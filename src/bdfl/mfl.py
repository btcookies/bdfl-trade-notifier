"""Client for the MyFantasyLeague export API."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from datetime import datetime

import requests

from bdfl.models import LeagueInfo, Player, as_list

BASE_URL = "https://api.myfantasyleague.com"
MIN_SECONDS_BETWEEN_REQUESTS = 1.0
DEFAULT_TYPES = "TRADE,BBID_WAIVER"

log = logging.getLogger(__name__)


class MflError(Exception):
    pass


class MflThrottled(MflError):
    pass


class LeagueNotFound(MflError):
    pass


class MflClient:
    def __init__(
        self,
        league_id: str,
        user_agent: str,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        timeout: float = 10.0,
    ):
        self.league_id = league_id
        self.user_agent = user_agent
        self.session = session or requests.Session()
        self.sleep = sleep
        self.clock = clock
        self.timeout = timeout
        self._last_request_at: float | None = None

    # --- public API ---------------------------------------------------------

    def league(self, year: int) -> dict | None:
        """Return the league element, or None when the year or league does not exist."""
        status, data = self._get(year, {"TYPE": "league"})
        if status != 200 or data is None or "error" in data:
            return None
        return data.get("league")

    def detect_league(self, now: datetime) -> LeagueInfo:
        for year in (now.year, now.year - 1):
            league = self.league(year)
            if league is None:
                continue
            years = {year}
            for entry in as_list((league.get("history") or {}).get("league")):
                value = str(entry.get("year", ""))
                if value.isdigit():
                    years.add(int(value))
            best = max(years)
            if best != year:
                newer = self.league(best)
                if newer is not None:
                    league = newer
                else:
                    best = year
            return LeagueInfo(
                year=best,
                name=str(league.get("name", "")),
                franchises={
                    f["id"]: f.get("name") or f"Franchise {f['id']}"
                    for f in as_list((league.get("franchises") or {}).get("franchise"))
                    if "id" in f
                },
            )
        raise LeagueNotFound(f"league {self.league_id} not found for {now.year} or {now.year - 1}")

    def transactions(self, year: int, days: int = 1, types: str = DEFAULT_TYPES) -> dict:
        status, data = self._get(
            year, {"TYPE": "transactions", "TRANS_TYPE": types, "DAYS": str(days)}
        )
        return self._require_ok(status, data, "transactions")

    def players(self, year: int, ids: Iterable[str]) -> dict[str, Player]:
        wanted = sorted(set(ids))
        if not wanted:
            return {}
        status, data = self._get(year, {"TYPE": "players", "PLAYERS": ",".join(wanted)})
        data = self._require_ok(status, data, "players")
        return {
            p["id"]: Player(
                id=p["id"],
                name=p.get("name", ""),
                team=p.get("team", ""),
                position=p.get("position", ""),
            )
            for p in as_list((data.get("players") or {}).get("player"))
            if "id" in p
        }

    # --- internals ----------------------------------------------------------

    def _require_ok(self, status: int, data: dict | None, what: str) -> dict:
        if status != 200 or data is None:
            raise MflError(f"MFL {what} request returned status {status}")
        if "error" in data:
            raise MflError(f"MFL {what} error: {data['error']}")
        return data

    def _get(self, year: int, params: dict) -> tuple[int, dict | None]:
        self._pace()
        query = {"TYPE": params["TYPE"], "L": self.league_id, "JSON": "1"}
        query.update({k: v for k, v in params.items() if k != "TYPE"})
        try:
            response = self.session.get(
                f"{BASE_URL}/{year}/export",
                params=query,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise MflError(f"MFL request failed: {exc}") from exc
        finally:
            self._last_request_at = self.clock()
        if response.status_code == 429:
            raise MflThrottled(f"MFL throttled TYPE={params['TYPE']} for {year}")
        if response.status_code == 404:
            return 404, None
        if response.status_code != 200:
            raise MflError(f"MFL returned {response.status_code} for TYPE={params['TYPE']}")
        try:
            return 200, response.json()
        except ValueError as exc:
            raise MflError("MFL returned a non-JSON body") from exc

    def _pace(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = self.clock() - self._last_request_at
        if elapsed < MIN_SECONDS_BETWEEN_REQUESTS:
            self.sleep(MIN_SECONDS_BETWEEN_REQUESTS - elapsed)
