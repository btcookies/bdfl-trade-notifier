"""Value over replacement: each start scored against a weekly positional baseline.

The baseline for a position in a week is the median score among every starter at that position
across every lineup MFL listed that week who actually has a recorded score. Rank the pool best
first and take the score at 1-based position (n + 1) // 2 for a pool of n starters: the 6th of
12 quarterbacks, the 12th of 24 running backs, the 7th of 13. A pool of one starter is its own
baseline. The median replaced the old N-th-best-starter rule (N = franchises times the position's
minimum starters) because a tanking franchise's lineup -- backups, practice-squad players,
anyone MFL would let them start -- could sink that low-ranked slot and drag replacement level
down with it. Those unrealistic scores now land in the tail of the ranked pool, not at its
center, so they no longer move the baseline.

A starter MFL never scored -- an eliminated or inactive franchise's stale lineup, not a real
0-point performance -- does not feed the pool at all: pooling it as a real 0.0 would still bias
the median low whenever such lineups make up a large share of a position's pool. A start in an
actual counted game with no recorded score still scores 0.0 points, same as always -- this only
changes who sets the baseline, not who gets scored against it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from hof.model.players import UNKNOWN_POSITION
from hof.model.season import Season

Baselines = dict[tuple[int, str], float]  # (week, position) -> replacement-level score


@dataclass(frozen=True)
class Start:
    year: int
    week: int
    franchise_id: str
    player_id: str
    position: str
    points: float
    vor: float
    playoff: bool


def baselines(season: Season) -> Baselines:
    result: Baselines = {}
    for week in season.weeks.values():
        pool: dict[str, list[float]] = defaultdict(list)
        for lineup in week.lineups.values():
            if not lineup.played:
                continue
            for player_id in lineup.starters:
                if player_id not in lineup.scores:
                    continue
                position = season.player(player_id).position
                if position != UNKNOWN_POSITION:
                    pool[position].append(lineup.points(player_id))
        for position, scores in pool.items():
            scores.sort(reverse=True)
            median_rank = (len(scores) + 1) // 2
            result[(week.number, position)] = scores[median_rank - 1]
    return result


def starts(season: Season) -> list[Start]:
    """One row per starter in every counted game, in week order."""
    base = baselines(season)
    rows: list[Start] = []
    for game in season.games():
        for lineup in (game.home, game.away):
            for player_id in lineup.starters:
                position = season.player(player_id).position
                points = lineup.points(player_id)
                if position == UNKNOWN_POSITION:
                    value = 0.0
                else:
                    value = round(points - base.get((game.week, position), 0.0), 1)
                rows.append(Start(season.year, game.week, lineup.franchise_id, player_id, position, points, value, game.playoff))
    return rows
