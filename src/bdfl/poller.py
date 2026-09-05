"""Per-invocation flow: fetch, dedupe, store, notify."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from bdfl.config import Settings
from bdfl.discord import DiscordError, DiscordPermanentError, DiscordWebhook
from bdfl.messages import (
    trade_details,
    trade_embed,
    trade_summary,
    waiver_details,
    waiver_messages,
    waiver_summary,
)
from bdfl.mfl import MflClient, MflThrottled
from bdfl.models import (
    LeagueInfo,
    Player,
    Record,
    Trade,
    WaiverClaim,
    parse_transactions,
    referenced_player_ids,
)
from bdfl.store import TransactionStore

BACKOFF_SECONDS = 300
LEAGUE_TTL_SECONDS = 6 * 3600
MAX_ATTEMPTS = 5
SEEN_CACHE_MAX = 2000
FINAL_STATES = {"sent", "skipped", "failed"}
# Discord allows roughly 5 webhook requests per 2 seconds; space posts out to stay under it.
POST_SPACING_SECONDS = 0.5
# Stop starting new posts after this long so one worst-case post (about 10 s of connect and read
# timeouts) and the final store writes still fit in Lambda's 30 s limit. The pathological
# 429-then-timeout post is bounded by the Lambda timeout itself; the outbox recovers next minute.
RUN_TIME_BUDGET_SECONDS = 12.0

log = logging.getLogger(__name__)


class NotifyFailed(Exception):
    pass


@dataclass
class PollResult:
    league_year: int | None = None
    fetched: int = 0
    new: int = 0
    skipped: int = 0
    sent: int = 0
    failed: int = 0
    deferred: int = 0
    store_errors: int = 0
    backoff: bool = False
    duration_ms: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def build_details(record: Record, league: LeagueInfo, players: dict[str, Player]) -> dict:
    if isinstance(record, Trade):
        return trade_details(record, league, players)
    return waiver_details(record, league, players)


def build_summary(record: Record, details: dict) -> str:
    if isinstance(record, Trade):
        return trade_summary(details)
    return waiver_summary(details)


def build_batches(
    to_notify: list[tuple[Record, dict]], league: LeagueInfo
) -> list[tuple[list[dict], list[Record]]]:
    """One message per trade in timestamp order, then the waiver digest for this batch."""
    ordered = sorted(to_notify, key=lambda pair: pair[0].timestamp)
    trades = [(r, d) for r, d in ordered if isinstance(r, Trade)]
    claims = [(r, d) for r, d in ordered if isinstance(r, WaiverClaim)]
    batches: list[tuple[list[dict], list[Record]]] = [
        ([trade_embed(r, d, league)], [r]) for r, d in trades
    ]
    batches += waiver_messages(claims, league)
    return batches


def make_item(record: Record, league: LeagueInfo, details: dict, state: str, now: float) -> dict:
    return {
        "pk": record.key,
        "type": record.type,
        "year": league.year,
        "timestamp": record.timestamp,
        "franchise_ids": record.franchise_ids,
        "raw": record.raw,
        "details": details,
        "summary": build_summary(record, details),
        "notify_state": state,
        "notify_attempts": 0,
        "first_seen_at": int(now),
        "notify_error": "",
    }


class Poller:
    """One MFL poll per invocation: fetch, dedupe through the table, notify, record the outcome.

    The DynamoDB table is the outbox and the only source of truth. Every warm cache on this
    object -- ``_league``, ``_seen``, ``_webhook``, ``_backoff_until`` -- is an optimization
    that survives between Lambda invocations on a warm container; correctness never depends
    on any of them, and a cold start that loses them all still behaves identically, just with
    more reads. In particular a key is remembered in ``_seen`` only after the store confirmed
    a terminal state for it, so a write the store never acknowledged is retried by the next
    poll rather than silently dropped.
    """

    def __init__(
        self,
        settings: Settings,
        mfl: MflClient,
        store: TransactionStore,
        webhook_factory: Callable[[], DiscordWebhook],
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.settings = settings
        self.mfl = mfl
        self.store = store
        self.webhook_factory = webhook_factory
        self.clock = clock
        self.sleep = sleep
        self._league: LeagueInfo | None = None
        self._league_at = 0.0
        self._backoff_until = 0.0
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._webhook: DiscordWebhook | None = None
        self.last_result: PollResult | None = None

    def run(self) -> PollResult:
        started = self.clock()
        result = PollResult()
        # Published before any work so the caller can log counts even when run() raises.
        self.last_result = result
        try:
            if started < self._backoff_until:
                result.backoff = True
                return result
            self._poll(started, result)
            return result
        except MflThrottled:
            self._backoff_until = self.clock() + BACKOFF_SECONDS
            log.warning("MFL throttled; backing off for %s seconds", BACKOFF_SECONDS)
            raise
        finally:
            result.duration_ms = int((self.clock() - started) * 1000)

    # --- steps --------------------------------------------------------------

    def _poll(self, started: float, result: PollResult) -> None:
        """``started`` is the single clock reading for this invocation: record ages, the
        ``notified_at`` stamp, and the run-time budget are all measured against it."""
        league, fetched_this_run = self._league_info(started)
        result.league_year = league.year
        records = parse_transactions(self.mfl.transactions(league.year))
        result.fetched = len(records)
        candidates = [r for r in records if r.key not in self._seen]
        existing = self.store.get_many([r.key for r in candidates]) if candidates else {}
        new_records = [r for r in candidates if r.key not in existing]
        league = self._ensure_franchises(league, new_records, started, fetched_this_run)
        to_notify = self._store_new(new_records, league, started, result)
        to_notify += self._pending_existing(candidates, existing, result)
        self._notify(to_notify, league, started, result)

    def _league_info(self, now: float) -> tuple[LeagueInfo, bool]:
        """Return the league info and whether this call fetched it rather than using the cache."""
        if self._league is None or now - self._league_at > LEAGUE_TTL_SECONDS:
            league = self.mfl.detect_league(datetime.fromtimestamp(now, tz=UTC))
            self._league = league
            self._league_at = now
            log.info("league year %s with %s franchises", league.year, len(league.franchises))
            return league, True
        return self._league, False

    def _ensure_franchises(
        self, league: LeagueInfo, records: list[Record], now: float, fetched_this_run: bool
    ) -> LeagueInfo:
        """Refresh league info when a record names an unknown franchise, at most once per run.

        A refresh is pointless when the info was already fetched this run: it would only ask
        MFL for the same answer again.
        """
        ids = {fid for r in records for fid in r.franchise_ids}
        if ids - set(league.franchises) and not fetched_this_run:
            self._league = None
            refreshed, _ = self._league_info(now)
            return refreshed
        return league

    def _store_new(
        self, new_records: list[Record], league: LeagueInfo, now: float, result: PollResult
    ) -> list[tuple[Record, dict]]:
        if not new_records:
            return []
        players = self.mfl.players(league.year, referenced_player_ids(new_records))
        to_notify: list[tuple[Record, dict]] = []
        for record in new_records:
            details = build_details(record, league, players)
            too_old = now - record.timestamp > self.settings.notify_max_age_seconds
            state = "skipped" if too_old else "pending"
            if not self.store.put_new(make_item(record, league, details, state, now)):
                log.warning("%s was stored concurrently; leaving it for the next poll", record.key)
                continue
            result.new += 1
            if too_old:
                result.skipped += 1
                self._remember(record.key)
            else:
                to_notify.append((record, details))
        return to_notify

    def _pending_existing(
        self, candidates: list[Record], existing: dict[str, dict], result: PollResult
    ) -> list[tuple[Record, dict]]:
        to_notify: list[tuple[Record, dict]] = []
        for record in candidates:
            row = existing.get(record.key)
            if row is None:
                continue
            state = row.get("notify_state")
            details = row.get("details")
            if state == "pending":
                try:
                    attempts = int(row.get("notify_attempts", 0))
                except (TypeError, ValueError):
                    log.warning(
                        "%s has an unusable notify_attempts (%r); treating it as final",
                        record.key,
                        row.get("notify_attempts"),
                    )
                    self._remember(record.key)
                    continue
                if attempts >= MAX_ATTEMPTS:
                    # A prior run exhausted it but could not record that; finish the transition now.
                    log.warning("%s is still pending after %s attempts; marking it failed", record.key, attempts)
                    reason = f"exhausted after {attempts} attempts (recovered)"
                    if self._store_update(result, self.store.mark_failed, record.key, reason) is not None:
                        self._remember(record.key)
                        result.failed += 1
                    continue
                if not isinstance(details, dict):
                    log.warning(
                        "%s has unusable details (%s); treating it as final",
                        record.key,
                        type(details).__name__,
                    )
                else:
                    to_notify.append((record, details))
                    continue
                self._remember(record.key)
                continue
            if state not in FINAL_STATES:
                log.warning(
                    "%s has an unexpected notify_state %r; treating it as final", record.key, state
                )
            self._remember(record.key)
        return to_notify

    def _notify(
        self,
        to_notify: list[tuple[Record, dict]],
        league: LeagueInfo,
        started: float,
        result: PollResult,
    ) -> None:
        """Post trades one message each in timestamp order, then the waiver digest for this poll."""
        if not to_notify:
            return
        batches = build_batches(to_notify, league)
        exhausted = False
        for index, (embeds, records) in enumerate(batches):
            if index:
                if self.clock() - started > RUN_TIME_BUDGET_SECONDS:
                    remaining = sum(len(r) for _, r in batches[index:])
                    log.warning(
                        "run time budget exhausted; deferring %s messages to the next poll",
                        remaining,
                    )
                    # The rows are still pending, so the next poll picks them back up.
                    result.deferred += remaining
                    break
                self.sleep(POST_SPACING_SECONDS)
            if not self._deliver(embeds, records, started, result):
                exhausted = True
        if exhausted:
            raise NotifyFailed("some notifications exhausted their attempts; see logs")

    def _deliver(
        self, embeds: list[dict], records: list[Record], now: float, result: PollResult
    ) -> bool:
        """Post one message. Returns False when a record can no longer be delivered."""
        try:
            self._webhook_client().post(embeds)
        except DiscordPermanentError as exc:
            log.error("Discord rejected %s permanently: %s", [r.key for r in records], exc)
            for record in records:
                reason = f"permanent: {exc}"[:500]
                if self._store_update(result, self.store.mark_failed, record.key, reason) is not None:
                    self._remember(record.key)
                    result.failed += 1
            return False
        except DiscordError as exc:
            log.error("Discord post failed for %s: %s", [r.key for r in records], exc)
            healthy = True
            for record in records:
                attempts = self._store_update(result, self.store.bump_attempt, record.key)
                if attempts is not None and attempts >= MAX_ATTEMPTS:
                    reason = f"exhausted after {attempts} attempts: {exc}"[:500]
                    if self._store_update(result, self.store.mark_failed, record.key, reason) is not None:
                        self._remember(record.key)
                        result.failed += 1
                    healthy = False
            return healthy
        for record in records:
            outcome = self._store_update(result, self.store.mark_sent, record.key, int(now))
            if outcome is None:
                continue  # store failed; leave the row pending and unremembered so the next poll reconciles
            self._remember(record.key)
            if outcome:
                result.sent += 1
        return True

    def _store_update(self, result: PollResult, operation: Callable[..., Any], *args: Any) -> Any:
        """Run a store update; a DynamoDB error must not abort the rest of the poll.

        Returns whatever the operation returned, ``True`` when it returned ``None`` without
        raising, and ``None`` only when the call failed -- so a caller can always tell a
        confirmed write from an unconfirmed one.
        """
        try:
            outcome = operation(*args)
        except (ClientError, BotoCoreError) as exc:
            result.store_errors += 1
            log.error("store update %s failed for %s: %s", operation.__name__, args[0], exc)
            return None
        return True if outcome is None else outcome

    # --- helpers ------------------------------------------------------------

    def _webhook_client(self) -> DiscordWebhook:
        if self._webhook is None:
            self._webhook = self.webhook_factory()
        return self._webhook

    def _remember(self, key: str) -> None:
        self._seen[key] = None
        self._seen.move_to_end(key)
        while len(self._seen) > SEEN_CACHE_MAX:
            self._seen.popitem(last=False)
