"""Value over replacement: each start scored against a weekly positional baseline.

The baseline for a position in a week is the score of the starter at 1-based rank
ceil(len(scores) * BASELINE_FRACTION) among every starter at that position across every lineup
MFL listed that week who actually has a recorded score, ranked best first: the 8th of 12
quarterbacks, the 16th of 24 running backs, the 9th of 13. A pool of one starter is its own
baseline. That rank sits at the top of the bottom third of starters at the position: below
average, since two-thirds of the pool outscored it, but above the tanking lineups that fill out
the bottom of the pool with backups and practice-squad players -- the same way baseball's
replacement level sits a fixed distance below average rather than at its center. The median was
tried and rejected: it compresses positions whose starters are bunched together, which drags the
baseline for tightly-packed positions up toward the middle of the pack instead of down near
replacement level.

A starter MFL never scored -- an eliminated or inactive franchise's stale lineup, not a real
0-point performance -- does not feed the pool at all: pooling it as a real 0.0 would still bias
the baseline low whenever such lineups make up a large share of a position's pool. A start in an
actual counted game with no recorded score still scores 0.0 points, same as always -- this only
changes who sets the baseline, not who gets scored against it.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from hof.model.players import UNKNOWN_POSITION
from hof.model.season import Season

Baselines = dict[tuple[int, str], float]  # (week, position) -> replacement-level score

BASELINE_FRACTION = 2 / 3


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
            baseline_rank = math.ceil(len(scores) * BASELINE_FRACTION)
            result[(week.number, position)] = scores[baseline_rank - 1]
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
