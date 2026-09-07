"""Value over replacement: each start scored against a weekly positional baseline.

The baseline for a position in a week is the N-th best score among every starter at that
position across every lineup MFL listed that week, where N is the number of franchises times
the position's minimum starters. Fewer than N starters means the lowest score is the baseline.
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
    franchise_count = len(season.franchises)
    result: Baselines = {}
    for week in season.weeks.values():
        pool: dict[str, list[float]] = defaultdict(list)
        for lineup in week.lineups.values():
            if not lineup.played:
                continue
            for player_id in lineup.starters:
                position = season.player(player_id).position
                if position != UNKNOWN_POSITION:
                    pool[position].append(lineup.points(player_id))
        for position, scores in pool.items():
            required = franchise_count * season.starter_minimums.get(position, 1)
            scores.sort(reverse=True)
            result[(week.number, position)] = scores[required - 1] if len(scores) >= required else scores[-1]
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
