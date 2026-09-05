"""Per-invocation flow: fetch, dedupe, store, notify."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import ClientError

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
POST_SPACING_SECONDS = 0.4

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
    }


class Poller:
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

    def run(self) -> PollResult:
        started = self.clock()
        result = PollResult()
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

    def _poll(self, now: float, result: PollResult) -> None:
        league = self._league_info(now)
        result.league_year = league.year
        records = parse_transactions(self.mfl.transactions(league.year))
        result.fetched = len(records)
        candidates = [r for r in records if r.key not in self._seen]
        existing = self.store.get_many([r.key for r in candidates]) if candidates else {}
        new_records = [r for r in candidates if r.key not in existing]
        league = self._ensure_franchises(league, new_records, now)
        to_notify = self._store_new(new_records, league, now, result)
        to_notify += self._pending_existing(candidates, existing)
        self._notify(to_notify, league, now, result)

    def _league_info(self, now: float) -> LeagueInfo:
        if self._league is None or now - self._league_at > LEAGUE_TTL_SECONDS:
            self._league = self.mfl.detect_league(datetime.fromtimestamp(now, tz=UTC))
            self._league_at = now
            log.info("league year %s with %s franchises", self._league.year, len(self._league.franchises))
        return self._league

    def _ensure_franchises(self, league: LeagueInfo, records: list[Record], now: float) -> LeagueInfo:
        """Refresh league info when a record names an unknown franchise, at most once per run."""
        ids = {fid for r in records for fid in r.franchise_ids}
        if ids - set(league.franchises) and self._league_at != now:
            self._league = None
            return self._league_info(now)
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
        self, candidates: list[Record], existing: dict[str, dict]
    ) -> list[tuple[Record, dict]]:
        to_notify: list[tuple[Record, dict]] = []
        for record in candidates:
            row = existing.get(record.key)
            if row is None:
                continue
            attempts = int(row.get("notify_attempts", 0))
            if row.get("notify_state") == "pending" and attempts < MAX_ATTEMPTS:
                to_notify.append((record, row["details"]))
            else:
                self._remember(record.key)
        return to_notify

    def _notify(
        self, to_notify: list[tuple[Record, dict]], league: LeagueInfo, now: float, result: PollResult
    ) -> None:
        if not to_notify:
            return
        trades = [(r, d) for r, d in to_notify if isinstance(r, Trade)]
        claims = [(r, d) for r, d in to_notify if isinstance(r, WaiverClaim)]
        batches: list[tuple[list[dict], list[Record]]] = [
            ([trade_embed(r, d, league)], [r]) for r, d in trades
        ]
        batches += waiver_messages(claims, league)
        exhausted = False
        for index, (embeds, records) in enumerate(batches):
            if index:
                self.sleep(POST_SPACING_SECONDS)
            if not self._deliver(embeds, records, now, result):
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
                self._store_update(self.store.mark_failed, record.key)
                self._remember(record.key)
                result.failed += 1
            return False
        except DiscordError as exc:
            log.error("Discord post failed for %s: %s", [r.key for r in records], exc)
            healthy = True
            for record in records:
                attempts = self._store_update(self.store.bump_attempt, record.key)
                if attempts is not None and attempts >= MAX_ATTEMPTS:
                    self._store_update(self.store.mark_failed, record.key)
                    self._remember(record.key)
                    result.failed += 1
                    healthy = False
            return healthy
        for record in records:
            if self._store_update(self.store.mark_sent, record.key, int(now)):
                result.sent += 1
            self._remember(record.key)
        return True

    def _store_update(self, operation: Callable[..., Any], *args: Any) -> Any:
        """Run a store update; a DynamoDB error must not abort the rest of the poll."""
        try:
            return operation(*args)
        except ClientError as exc:
            log.error("store update %s failed for %s: %s", operation.__name__, args[0], exc)
            return None

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
