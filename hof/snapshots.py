"""Load raw season snapshots from data/raw/<year>/ into Season objects."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from hof.model.players import parse_players
from hof.model.season import (
    Season,
    parse_bracket,
    parse_draft,
    parse_league,
    parse_standings,
    parse_week,
)
from hof.model.transactions import parse_transactions

log = logging.getLogger(__name__)

WEEK_FILE = re.compile(r"^W(\d{2})\.json$")


def read_json(path: Path) -> dict[str, Any]:
    """The parsed file, or an empty dict with a warning when it is missing or unreadable."""
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        log.warning("missing snapshot %s", path)
        return {}
    except ValueError as exc:
        log.warning("unreadable snapshot %s: %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def load_season(season_dir: Path) -> Season:
    year = int(season_dir.name)
    meta = read_json(season_dir / "meta.json")
    settings = parse_league(read_json(season_dir / "league.json"))
    weeks = {}
    for path in sorted((season_dir / "weeklyResults").glob("W*.json")):
        match = WEEK_FILE.match(path.name)
        if match is None:
            continue
        week = parse_week(read_json(path), number=int(match.group(1)))
        weeks[week.number] = week
    draft, round1_order = parse_draft(read_json(season_dir / "draftResults.json"))
    return Season(
        year=year,
        league_id=str(meta.get("league_id") or ""),
        name=settings.name,
        complete=bool(meta.get("complete")),
        franchises=settings.franchises,
        starter_minimums=settings.starter_minimums,
        start_week=settings.start_week,
        end_week=settings.end_week,
        last_regular_season_week=settings.last_regular_season_week,
        weeks=weeks,
        bracket=parse_bracket(read_json(season_dir / "playoffBracket-1.json")),
        standings=parse_standings(read_json(season_dir / "standings.json")),
        draft=draft,
        round1_order=round1_order,
        transactions=parse_transactions(read_json(season_dir / "transactions.json")),
        players=parse_players(read_json(season_dir / "players.json")),
    )


def load_all(data_dir: Path) -> list[Season]:
    """Every season under data_dir/raw, oldest first."""
    raw = data_dir / "raw"
    if not raw.exists():
        return []
    season_dirs = sorted(p for p in raw.iterdir() if p.is_dir() and p.name.isdigit())
    return [load_season(p) for p in season_dirs]
