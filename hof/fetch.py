"""Fetch raw MFL exports for every season into data/raw/<year>/.

Completed seasons are fetched once and never touched again. The current season is refetched
in full on every run so stat corrections flow through. A season directory is replaced only
after every request for it succeeded.
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Callable, Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from bdfl.mfl import LeagueNotFound, MflClient
from bdfl.models import as_list, split_assets
from hof.config import Config

log = logging.getLogger(__name__)

USER_AGENT = "bdfl-hof/1.0 (+https://github.com/btcookies/bdfl-trade-notifier)"
PLAYERS_CHUNK = 200
TRANSACTIONS_DAYS = "400"

# (file name, TYPE, extra params). Weekly results and players are fetched separately.
SEASON_EXPORTS: tuple[tuple[str, str, dict[str, str]], ...] = (
    ("league.json", "league", {}),
    ("standings.json", "standings", {}),
    ("schedule.json", "schedule", {}),
    ("playoffBrackets.json", "playoffBrackets", {}),
    ("playoffBracket-1.json", "playoffBracket", {"BRACKET_ID": "1"}),
    ("draftResults.json", "draftResults", {}),
    ("transactions.json", "transactions", {"TRANS_TYPE": "*", "DAYS": TRANSACTIONS_DAYS}),
)

ClientFactory = Callable[[str], MflClient]


def season_complete(year: int, today: date) -> bool:
    """A season is frozen once February of the following year arrives."""
    return today >= date(year + 1, 2, 1)


def discover_seasons(client: MflClient, now: datetime) -> list[int]:
    """Every season year in the current league's history, oldest first."""
    for year in (now.year, now.year - 1):
        league = client.league(year)
        if league is None:
            continue
        years = {
            int(entry["year"])
            for entry in as_list((league.get("history") or {}).get("league"))
            if str(entry.get("year", "")).isdigit()
        }
        years.add(year)
        return sorted(years)
    raise LeagueNotFound(f"league {client.league_id} not found for {now.year} or {now.year - 1}")


def is_fetched_complete(season_dir: Path) -> bool:
    meta = season_dir / "meta.json"
    if not meta.exists():
        return False
    try:
        return bool(json.loads(meta.read_text()).get("complete"))
    except (ValueError, OSError):
        return False


def write_json(path: Path, body: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=1, sort_keys=True, ensure_ascii=False) + "\n")


def _lineups(weekly_body: dict[str, Any]) -> list[dict[str, Any]]:
    results = weekly_body.get("weeklyResults") or {}
    matchup_lineups = [
        franchise
        for matchup in as_list(results.get("matchup"))
        for franchise in as_list(matchup.get("franchise"))
    ]
    return matchup_lineups + as_list(results.get("franchise"))


def referenced_player_ids(
    weekly: Iterable[dict[str, Any]], draft: dict[str, Any], transactions: dict[str, Any]
) -> set[str]:
    """Every player id a season's lineups, draft, and transaction log mention."""
    ids: set[str] = set()
    for body in weekly:
        for lineup in _lineups(body):
            ids.update(split_assets(lineup.get("starters")))
            ids.update(split_assets(lineup.get("nonstarters")))
            ids.update(str(p["id"]) for p in as_list(lineup.get("player")) if "id" in p)
    for unit in as_list((draft.get("draftResults") or {}).get("draftUnit")):
        ids.update(str(p["player"]) for p in as_list(unit.get("draftPick")) if p.get("player"))
    for tx in as_list((transactions.get("transactions") or {}).get("transaction")):
        for key in ("franchise1_gave_up", "franchise2_gave_up", "activated", "deactivated", "promoted", "demoted"):
            ids.update(split_assets(tx.get(key)))
        for part in str(tx.get("transaction") or "").split("|"):
            ids.update(split_assets(part))
    return {i for i in ids if i.isdigit()}


def fetch_players(client: MflClient, year: int, ids: Iterable[str]) -> dict[str, Any]:
    """One merged players export for the ids, requested in chunks of PLAYERS_CHUNK."""
    wanted = sorted(set(ids))
    players: list[dict[str, Any]] = []
    for start in range(0, len(wanted), PLAYERS_CHUNK):
        chunk = wanted[start : start + PLAYERS_CHUNK]
        body = client.export(year, "players", PLAYERS=",".join(chunk))
        players.extend(as_list((body.get("players") or {}).get("player")))
    return {"players": {"player": players}}


def fetch_season(client: MflClient, year: int, season_dir: Path, now: datetime) -> None:
    """Fetch every export for one season, replacing season_dir only on full success."""
    tmp = season_dir.parent / f".{year}.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    try:
        bodies: dict[str, dict[str, Any]] = {}
        for name, type_, params in SEASON_EXPORTS:
            bodies[name] = client.export(year, type_, **params)
            write_json(tmp / name, bodies[name])
        league = bodies["league.json"].get("league") or {}
        start_week = int(league.get("startWeek") or 1)
        end_week = int(league.get("endWeek") or 17)
        weekly: list[dict[str, Any]] = []
        for week in range(start_week, end_week + 1):
            body = client.export(year, "weeklyResults", W=str(week))
            write_json(tmp / "weeklyResults" / f"W{week:02d}.json", body)
            weekly.append(body)
        ids = referenced_player_ids(weekly, bodies["draftResults.json"], bodies["transactions.json"])
        write_json(tmp / "players.json", fetch_players(client, year, ids))
        write_json(
            tmp / "meta.json",
            {
                "league_id": client.league_id,
                "complete": season_complete(year, now.date()),
                "fetched_at": now.isoformat(timespec="seconds"),
                "weeks": [start_week, end_week],
            },
        )
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    if season_dir.exists():
        shutil.rmtree(season_dir)
    tmp.rename(season_dir)


def run(
    data_dir: Path,
    config: Config,
    now: datetime,
    client_factory: ClientFactory,
    years: Iterable[int] | None = None,
) -> list[int]:
    """Fetch every season not already complete on disk; return the years fetched, ascending."""
    raw = data_dir / "raw"
    current = client_factory(config.league_id)
    wanted = sorted(years) if years is not None else discover_seasons(current, now)
    fetched: list[int] = []
    for year in wanted:
        season_dir = raw / str(year)
        if is_fetched_complete(season_dir):
            log.info("season %s already complete; skipping", year)
            continue
        league_id = config.league_id_for(year)
        client = current if league_id == config.league_id else client_factory(league_id)
        log.info("fetching season %s from league %s", year, league_id)
        fetch_season(client, year, season_dir, now)
        fetched.append(year)
    return fetched
