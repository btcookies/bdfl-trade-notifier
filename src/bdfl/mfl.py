"""Client for the MyFantasyLeague export API."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

from bdfl.models import LeagueInfo, Player, as_list

BASE_URL = "https://api.myfantasyleague.com"
MIN_SECONDS_BETWEEN_REQUESTS = 1.0
CONNECTION_RETRIES = 2  # extra attempts after a transient connection error, not an HTTP error
DEFAULT_TYPES = "TRADE,BBID_WAIVER"

log = logging.getLogger(__name__)


class MflError(Exception):
    pass


class MflThrottled(MflError):
    pass


class MflNotFound(MflError):
    """The year or league does not exist (HTTP 404)."""


class LeagueNotFound(MflError):
    pass


@dataclass
class RequestPacer:
    """Last-request timestamp, shared across every MflClient that passes the same instance in.

    Pacing lives here rather than on MflClient itself so that multiple clients reusing one
    requests.Session (e.g. one per MFL league id, all hitting the same host) collectively
    respect the one-request-per-second limit -- otherwise a freshly built client has no memory
    of a sibling client's last request and fires immediately, which can hit the shared
    connection before the server is done with it.
    """

    last_request_at: float | None = None


class MflClient:
    def __init__(
        self,
        league_id: str,
        user_agent: str,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        timeout: float | tuple[float, float] = (3.05, 7.0),
        pacer: RequestPacer | None = None,
    ):
        self.league_id = league_id
        self.user_agent = user_agent
        self.session = session or requests.Session()
        self.sleep = sleep
        self.clock = clock
        self.timeout = timeout
        self.pacer = pacer if pacer is not None else RequestPacer()

    # --- public API ---------------------------------------------------------

    def league(self, year: int) -> dict[str, Any] | None:
        """Return the league element, or None when the year or league does not exist."""
        try:
            data = self._get(year, "league")
        except MflNotFound:
            return None
        if "error" in data:
            log.warning("MFL league export error for %s: %s", year, data["error"])
            return None
        return data.get("league")

    def detect_league(self, now: datetime) -> LeagueInfo:
        """Return the league as of the current calendar year, or the prior year before rollover.

        MFL's league export lists every season in `history`, but the newest season a poller
        should follow is always the current calendar year when it exists, and the prior year
        otherwise, so the history list is intentionally not consulted here.
        """
        for year in (now.year, now.year - 1):
            league = self.league(year)
            if league is None:
                continue
            info = LeagueInfo(
                year=year,
                name=str(league.get("name", "")).strip(),
                franchises={
                    f["id"]: str(f.get("name") or "").strip() or f"Franchise {f['id']}"
                    for f in as_list((league.get("franchises") or {}).get("franchise"))
                    if "id" in f
                },
            )
            log.info("using MFL league year %s (%s franchises)", info.year, len(info.franchises))
            return info
        raise LeagueNotFound(f"league {self.league_id} not found for {now.year} or {now.year - 1}")

    def transactions(self, year: int, days: int = 1, types: str = DEFAULT_TYPES) -> dict[str, Any]:
        data = self._get(year, "transactions", TRANS_TYPE=types, DAYS=str(days))
        return self._require_ok(data, "transactions")

    def players(self, year: int, ids: Iterable[str]) -> dict[str, Player]:
        wanted = sorted(set(ids))
        if not wanted:
            return {}
        data = self._get(year, "players", PLAYERS=",".join(wanted))
        data = self._require_ok(data, "players")
        return {
            str(p["id"]).strip(): Player(
                id=str(p["id"]).strip(),
                name=str(p.get("name", "")).strip(),
                team=str(p.get("team", "")).strip(),
                position=str(p.get("position", "")).strip(),
            )
            for p in as_list((data.get("players") or {}).get("player"))
            if "id" in p
        }

    def export(self, year: int, type_: str, **params: str) -> dict[str, Any]:
        """Fetch any export TYPE for a year and return the parsed body.

        Raises MflError on an error body; the hall of records uses this for every export
        the notifier does not need by name.
        """
        return self._require_ok(self._get(year, type_, **params), type_)

    # --- internals ----------------------------------------------------------

    def _require_ok(self, data: dict[str, Any], what: str) -> dict[str, Any]:
        if "error" in data:
            raise MflError(f"MFL {what} error: {data['error']}")
        return data

    def _get(self, year: int, type_: str, **extra: str) -> dict[str, Any]:
        query = {"TYPE": type_, "L": self.league_id, "JSON": "1", **extra}
        response = self._request(year, query)
        if response.status_code == 429:
            raise MflThrottled(f"MFL throttled TYPE={type_} for {year}")
        if response.status_code == 404:
            raise MflNotFound(f"MFL has no {type_} export for {year}")
        if response.status_code != 200:
            raise MflError(f"MFL returned {response.status_code} for TYPE={type_}")
        try:
            data = response.json()
        except ValueError as exc:
            raise MflError("MFL returned a non-JSON body") from exc
        if not isinstance(data, dict):
            raise MflError("MFL returned a non-object JSON body")
        return data

    def _request(self, year: int, query: dict[str, str]) -> requests.Response:
        """GET, retrying a transient connection reset a couple of times.

        MFL's server occasionally resets a pooled keep-alive connection right around our
        one-per-second pacing gap -- not a rate-limit signal (that's a 429, handled by the
        caller), just server-side flakiness worth one or two retries before giving up. Only a
        ConnectionError is retried: this client is shared with the notifier Lambda's tight
        processing budget, and blindly retrying a slow request that times out could blow it.
        """
        last_exc: requests.RequestException | None = None
        for attempt in range(CONNECTION_RETRIES + 1):
            self._pace()
            try:
                return self.session.get(
                    f"{BASE_URL}/{year}/export",
                    params=query,
                    headers={"User-Agent": self.user_agent},
                    timeout=self.timeout,
                )
            except requests.ConnectionError as exc:
                last_exc = exc
                if attempt < CONNECTION_RETRIES:
                    log.warning(
                        "MFL connection error for %s (attempt %d/%d), retrying: %s",
                        query.get("TYPE"), attempt + 1, CONNECTION_RETRIES + 1, exc,
                    )
            except requests.RequestException as exc:
                last_exc = exc
                break
            finally:
                # In a finally so a failed request still counts against MFL's one-per-second rule.
                self.pacer.last_request_at = self.clock()
        # The URL carries only public ids today; if an APIKEY is ever added, redact it here.
        raise MflError(f"MFL request failed: {last_exc}") from last_exc

    def _pace(self) -> None:
        if self.pacer.last_request_at is None:
            return
        elapsed = self.clock() - self.pacer.last_request_at
        if elapsed < MIN_SECONDS_BETWEEN_REQUESTS:
            self.sleep(MIN_SECONDS_BETWEEN_REQUESTS - elapsed)
