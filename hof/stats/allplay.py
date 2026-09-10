"""All-play records and luck: every franchise against every other counted score, week by week.

A week's all-play record is out of (franchises with a counted score that week) - 1. Expected
wins for a week is the all-play win share; season expected wins is the sum over weeks played;
luck is actual wins (ties count half) minus expected wins. Playoff weeks are excluded because
not every franchise plays a counted game.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from hof.model.season import Season
from hof.stats.league import League


@dataclass(frozen=True)
class AllPlayWeek:
    """One franchise's week measured against every other counted score that week."""

    franchise_id: str
    week: int
    wins: int
    losses: int
    ties: int

    @property
    def expected_wins(self) -> float:
        compared = self.wins + self.losses + self.ties
        return (self.wins + 0.5 * self.ties) / compared if compared else 0.0

    @property
    def record(self) -> str:
        return f"{self.wins}-{self.losses}-{self.ties}"


@dataclass(frozen=True)
class StandingLine:
    """A franchise's regular-season line through a week, with its all-play record and luck."""

    franchise_id: str
    name: str  # the name used that season
    wins: int
    losses: int
    ties: int
    points_for: float
    points_against: float
    allplay: tuple[int, int, int]
    expected_wins: float  # two decimals
    luck: float  # one decimal, signed

    @property
    def games(self) -> int:
        return self.wins + self.losses + self.ties

    @property
    def record(self) -> str:
        return f"{self.wins}-{self.losses}-{self.ties}"

    @property
    def allplay_record(self) -> str:
        return "-".join(str(n) for n in self.allplay)

    @property
    def allplay_pct(self) -> float:
        wins, losses, ties = self.allplay
        total = wins + losses + ties
        return (wins + 0.5 * ties) / total if total else 0.0


def scores_by_week(season: Season) -> dict[int, dict[str, float]]:
    """week -> franchise id -> counted regular-season score, from one pass over the games."""
    out: dict[int, dict[str, float]] = {}
    for game in season.games():
        if game.playoff:
            continue
        week = out.setdefault(game.week, {})
        for lineup in (game.home, game.away):
            week[lineup.franchise_id] = lineup.score or 0.0
    return out


def regular_weeks(season: Season, through_week: int | None = None) -> list[int]:
    """Regular-season weeks with at least one counted game, ascending, up to through_week."""
    weeks = sorted(scores_by_week(season))
    if through_week is not None:
        weeks = [w for w in weeks if w <= through_week]
    return weeks


def _rows(week: int, scores: dict[str, float]) -> list[AllPlayWeek]:
    """One row per franchise with a counted score, by id; none when fewer than two scored."""
    if len(scores) < 2:
        return []
    rows: list[AllPlayWeek] = []
    for fid, score in sorted(scores.items()):
        others = [s for other, s in scores.items() if other != fid]
        rows.append(
            AllPlayWeek(
                franchise_id=fid,
                week=week,
                wins=sum(1 for s in others if score > s),
                losses=sum(1 for s in others if score < s),
                ties=sum(1 for s in others if score == s),
            )
        )
    return rows


def all_play_week(season: Season, week: int) -> list[AllPlayWeek]:
    return _rows(week, scores_by_week(season).get(week, {}))


def all_play_weeks(season: Season, through_week: int | None = None) -> list[AllPlayWeek]:
    by_week = scores_by_week(season)
    return [
        row
        for week in sorted(by_week)
        if through_week is None or week <= through_week
        for row in _rows(week, by_week[week])
    ]


def _order(season: Season, through_week: int | None) -> Callable[[StandingLine], tuple]:
    """MFL's standings order when the export is present and the lines are current; else by
    win percentage, points for, and name."""
    newest = regular_weeks(season)
    current = through_week is None or (bool(newest) and through_week >= newest[-1])
    if season.standings and current:
        position = {s.franchise_id: i for i, s in enumerate(season.standings)}
        return lambda line: (position.get(line.franchise_id, len(position)), line.name)
    return lambda line: (-(line.wins + 0.5 * line.ties), -line.points_for, line.name)


def standings(
    league: League, season: Season, through_week: int | None = None
) -> list[StandingLine]:
    """Every franchise's regular-season line through the week (every week when None)."""
    weeks = set(regular_weeks(season, through_week))
    ids = list(season.franchises)
    wins = dict.fromkeys(ids, 0)
    losses = dict.fromkeys(ids, 0)
    ties = dict.fromkeys(ids, 0)
    points_for = dict.fromkeys(ids, 0.0)
    points_against = dict.fromkeys(ids, 0.0)
    for game in season.games():
        if game.playoff or game.week not in weeks:
            continue
        for own, other in ((game.home, game.away), (game.away, game.home)):
            fid = own.franchise_id
            own_score, other_score = own.score or 0.0, other.score or 0.0
            points_for[fid] = points_for.get(fid, 0.0) + own_score
            points_against[fid] = points_against.get(fid, 0.0) + other_score
            if own_score > other_score:
                wins[fid] = wins.get(fid, 0) + 1
            elif own_score < other_score:
                losses[fid] = losses.get(fid, 0) + 1
            else:
                ties[fid] = ties.get(fid, 0) + 1
    allplay: dict[str, list[int]] = {fid: [0, 0, 0] for fid in ids}
    expected = dict.fromkeys(ids, 0.0)
    for row in all_play_weeks(season, through_week):
        record = allplay.setdefault(row.franchise_id, [0, 0, 0])
        record[0] += row.wins
        record[1] += row.losses
        record[2] += row.ties
        expected[row.franchise_id] = expected.get(row.franchise_id, 0.0) + row.expected_wins
    lines = [
        StandingLine(
            franchise_id=fid,
            name=league.name_in(fid, season.year),
            wins=wins.get(fid, 0),
            losses=losses.get(fid, 0),
            ties=ties.get(fid, 0),
            points_for=round(points_for.get(fid, 0.0), 1),
            points_against=round(points_against.get(fid, 0.0), 1),
            allplay=(allplay[fid][0], allplay[fid][1], allplay[fid][2]),
            expected_wins=round(expected.get(fid, 0.0), 2),
            luck=round(wins.get(fid, 0) + 0.5 * ties.get(fid, 0) - expected.get(fid, 0.0), 1),
        )
        for fid in set(ids) | set(allplay)
    ]
    return sorted(lines, key=_order(season, through_week))
