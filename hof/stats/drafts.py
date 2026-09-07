"""Draft hindsight: what every pick produced for the franchise that made it."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from hof.model.season import DraftPick, normalize_name
from hof.stats.careers import Career
from hof.stats.league import League

STARTUP_ROUNDS = 10  # a draft with at least this many rounds is a startup draft, not a rookie draft
TRADED_FROM = "Pick traded from "


@dataclass(frozen=True)
class PickLine:
    year: int
    round: int
    pick: int
    franchise_id: str
    franchise_name: str  # at the time
    original_owner_id: str | None
    player_id: str
    player_name: str
    position: str
    starts_for: int  # as a starter for the drafting franchise, ever
    points_for: float
    vor_for: float
    career_points: float
    career_vor: float


@dataclass(frozen=True)
class DraftSummary:
    year: int
    startup: bool
    rounds: int
    picks: tuple[PickLine, ...]  # draft order
    steal: PickLine | None  # best value outside round one
    bust: PickLine | None  # worst value in round one


@dataclass(frozen=True)
class DraftRanking:
    franchise_id: str
    name: str  # current name
    picks: int
    vor: float


def chain(comments: str) -> list[str]:
    """Franchise names in the pick's 'Pick traded from' lines, oldest first."""
    names: list[str] = []
    for line in comments.strip().strip("[]").splitlines():
        text = line.strip().strip("[]").strip()
        if text.startswith(TRADED_FROM):
            names.append(text[len(TRADED_FROM) :].rstrip(".").strip())
    return names


def original_owner(pick: DraftPick, by_name: dict[str, str]) -> str | None:
    """The franchise the pick originally belonged to; None when the chain names nobody we know."""
    names = chain(pick.comments)
    if not names:
        return pick.franchise_id
    return by_name.get(normalize_name(names[0]))


def value_for(league: League) -> dict[tuple[str, str], tuple[int, float, float]]:
    """(player id, franchise id) -> (starts, points, vor) as a starter for that franchise."""
    totals: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0, 0.0, 0.0])
    for row in league.all_starts():
        entry = totals[(row.player_id, row.franchise_id)]
        entry[0] += 1
        entry[1] += row.points
        entry[2] += row.vor
    return {key: (int(v[0]), round(v[1], 1), round(v[2], 1)) for key, v in totals.items()}


def draft_summaries(league: League, careers: dict[str, Career]) -> list[DraftSummary]:
    by_name = league.franchise_by_name()
    values = value_for(league)
    summaries: list[DraftSummary] = []
    for season in league.seasons:
        if not season.draft:
            continue
        lines: list[PickLine] = []
        for pick in season.draft:
            starts, points, vor = values.get((pick.player_id, pick.franchise_id), (0, 0.0, 0.0))
            career = careers.get(pick.player_id)
            info = league.player_info(pick.player_id)
            lines.append(
                PickLine(
                    year=season.year,
                    round=pick.round,
                    pick=pick.pick,
                    franchise_id=pick.franchise_id,
                    franchise_name=league.name_in(pick.franchise_id, season.year),
                    original_owner_id=original_owner(pick, by_name),
                    player_id=pick.player_id,
                    player_name=info.name,
                    position=info.position,
                    starts_for=starts,
                    points_for=points,
                    vor_for=vor,
                    career_points=career.points if career else 0.0,
                    career_vor=career.vor if career else 0.0,
                )
            )
        rounds = max(line.round for line in lines)
        later = [line for line in lines if line.round > 1]
        first = [line for line in lines if line.round == 1]
        summaries.append(
            DraftSummary(
                year=season.year,
                startup=rounds >= STARTUP_ROUNDS,
                rounds=rounds,
                picks=tuple(lines),
                steal=max(later, key=lambda line: (line.vor_for, -line.round, -line.pick), default=None),
                bust=min(first, key=lambda line: (line.vor_for, line.pick), default=None),
            )
        )
    return summaries


def draft_rankings(league: League, summaries: list[DraftSummary]) -> list[DraftRanking]:
    picks: dict[str, int] = defaultdict(int)
    vor: dict[str, float] = defaultdict(float)
    for summary in summaries:
        for line in summary.picks:
            picks[line.franchise_id] += 1
            vor[line.franchise_id] += line.vor_for
    rankings = [DraftRanking(fid, league.current_name(fid), picks[fid], round(vor[fid], 1)) for fid in picks]
    return sorted(rankings, key=lambda r: (-r.vor, r.name))
