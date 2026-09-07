"""Hall of Fame: rule-based induction evaluated season by season, plus the watch list."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from hof.config import HallRules
from hof.stats.careers import Career
from hof.stats.franchises import FranchiseHistory
from hof.stats.league import League
from hof.stats.records import finished


@dataclass(frozen=True)
class PlayerPlaque:
    player_id: str
    name: str
    position: str
    class_year: int
    franchise_names: tuple[str, ...]  # current names, in order of first stint
    starts: int
    points: float
    vor: float
    titles: int


@dataclass(frozen=True)
class FranchisePlaque:
    franchise_id: str
    name: str
    class_year: int
    titles: int
    record: str
    win_pct: float


@dataclass(frozen=True)
class WatchEntry:
    player_id: str
    name: str
    position: str
    starts: int
    vor: float
    needed_vor: float
    needed_starts: int


@dataclass(frozen=True)
class Hall:
    players: tuple[PlayerPlaque, ...]  # by class year, then value
    franchises: tuple[FranchisePlaque, ...]
    watch_list: tuple[WatchEntry, ...]  # closest to the line first
    rules: HallRules


def player_class_years(league: League, rules: HallRules) -> dict[str, int]:
    """Player id -> the finished season at whose end they crossed both thresholds."""
    starts: dict[str, int] = defaultdict(int)
    vor: dict[str, float] = defaultdict(float)
    inducted: dict[str, int] = {}
    for season in league.seasons:
        if not finished(season):
            continue
        for row in league.starts[season.year]:
            starts[row.player_id] += 1
            vor[row.player_id] += row.vor
        for pid in vor:
            if pid not in inducted and vor[pid] >= rules.player_min_vor and starts[pid] >= rules.player_min_starts:
                inducted[pid] = season.year
    return inducted


def franchise_class_years(league: League, rules: HallRules) -> dict[str, int]:
    """Franchise id -> the season of its qualifying title."""
    titles: dict[str, int] = defaultdict(int)
    inducted: dict[str, int] = {}
    for season in league.seasons:
        champion = season.champion_id
        if champion is None:
            continue
        titles[champion] += 1
        if champion not in inducted and titles[champion] >= rules.franchise_min_titles:
            inducted[champion] = season.year
    return inducted


def hall_of_fame(
    league: League,
    careers: dict[str, Career],
    histories: dict[str, FranchiseHistory],
    rules: HallRules,
) -> Hall:
    player_years = player_class_years(league, rules)
    players = [
        PlayerPlaque(
            player_id=pid,
            name=career.name,
            position=career.position,
            class_year=year,
            franchise_names=tuple(league.current_name(fid) for fid in career.franchise_ids),
            starts=career.starts,
            points=career.points,
            vor=career.vor,
            titles=career.titles,
        )
        for pid, year in player_years.items()
        if (career := careers.get(pid)) is not None
    ]
    franchise_years = franchise_class_years(league, rules)
    plaques = [
        FranchisePlaque(fid, history.name, year, history.totals.titles, history.totals.record, round(history.totals.win_pct, 3))
        for fid, year in franchise_years.items()
        if (history := histories.get(fid)) is not None
    ]
    watch = [
        WatchEntry(
            player_id=career.player_id,
            name=career.name,
            position=career.position,
            starts=career.starts,
            vor=career.vor,
            needed_vor=round(max(0.0, rules.player_min_vor - career.vor), 1),
            needed_starts=max(0, rules.player_min_starts - career.starts),
        )
        for career in careers.values()
        if career.active and career.player_id not in player_years and career.vor >= rules.player_min_vor - rules.watch_list_margin
    ]
    return Hall(
        players=tuple(sorted(players, key=lambda p: (p.class_year, -p.vor, p.name))),
        franchises=tuple(sorted(plaques, key=lambda p: (p.class_year, p.name))),
        watch_list=tuple(sorted(watch, key=lambda w: (w.needed_vor, w.needed_starts, w.name))),
        rules=rules,
    )
