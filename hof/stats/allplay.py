"""All-play records and luck: every franchise against every other counted score, week by week.

A week's all-play record is out of (franchises with a counted score that week) - 1. Expected
wins for a week is the all-play win share; season expected wins is the sum over weeks played;
luck is actual wins (ties count half) minus expected wins. Playoff weeks are excluded because
not every franchise plays a counted game.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from hof.model.season import Game, Season
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


def _regular_games(season: Season) -> list[Game]:
    return [game for game in season.games() if not game.playoff]


def _scores_by_week(games: list[Game]) -> dict[int, dict[str, float]]:
    out: dict[int, dict[str, float]] = {}
    for game in games:
        week = out.setdefault(game.week, {})
        for lineup in (game.home, game.away):
            week[lineup.franchise_id] = lineup.score or 0.0
    return out


def scores_by_week(season: Season) -> dict[int, dict[str, float]]:
    """week -> franchise id -> counted regular-season score, from one pass over the games."""
    return _scores_by_week(_regular_games(season))


def regular_weeks(season: Season, through_week: int | None = None) -> list[int]:
    """Regular-season weeks with at least one counted game, ascending, up to through_week."""
    return _weeks_through(scores_by_week(season), through_week)


def _weeks_through(by_week: dict[int, dict[str, float]], through_week: int | None) -> list[int]:
    return [week for week in sorted(by_week) if through_week is None or week <= through_week]


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
    return [row for week in _weeks_through(by_week, through_week) for row in _rows(week, by_week[week])]


def _order(season: Season, through_week: int | None, newest_week: int | None) -> Callable[[StandingLine], tuple]:
    """MFL's standings order when the export is present and the lines are current; else by
    win percentage, points for, and name."""
    current = through_week is None or (newest_week is not None and through_week >= newest_week)
    if season.standings and current:
        position = {s.franchise_id: i for i, s in enumerate(season.standings)}
        return lambda line: (position.get(line.franchise_id, len(position)), line.name)

    def pct(line: StandingLine) -> float:
        return (line.wins + 0.5 * line.ties) / line.games if line.games else 0.0

    return lambda line: (-pct(line), -line.points_for, line.name)


def standings(league: League, season: Season, through_week: int | None = None) -> list[StandingLine]:
    """Every franchise's regular-season line through the week (every week when None)."""
    games = _regular_games(season)
    by_week = _scores_by_week(games)
    weeks = _weeks_through(by_week, through_week)
    counted = set(weeks)
    wins: dict[str, int] = defaultdict(int)
    losses: dict[str, int] = defaultdict(int)
    ties: dict[str, int] = defaultdict(int)
    points_for: dict[str, float] = defaultdict(float)
    points_against: dict[str, float] = defaultdict(float)
    for game in games:
        if game.week not in counted:
            continue
        for own, other in ((game.home, game.away), (game.away, game.home)):
            fid = own.franchise_id
            own_score, other_score = own.score or 0.0, other.score or 0.0
            points_for[fid] += own_score
            points_against[fid] += other_score
            if own_score > other_score:
                wins[fid] += 1
            elif own_score < other_score:
                losses[fid] += 1
            else:
                ties[fid] += 1
    allplay_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    expected: dict[str, float] = defaultdict(float)
    for week in weeks:
        for row in _rows(week, by_week[week]):
            totals = allplay_totals[row.franchise_id]
            totals[0] += row.wins
            totals[1] += row.losses
            totals[2] += row.ties
            expected[row.franchise_id] += row.expected_wins
    ids = set(season.franchises) | set(points_for)
    lines = [
        StandingLine(
            franchise_id=fid,
            name=league.name_in(fid, season.year),
            wins=wins[fid],
            losses=losses[fid],
            ties=ties[fid],
            points_for=round(points_for[fid], 1),
            points_against=round(points_against[fid], 1),
            allplay=tuple(allplay_totals.get(fid, [0, 0, 0])),
            expected_wins=round(expected[fid], 2),
            luck=round(wins[fid] + 0.5 * ties[fid] - expected[fid], 1),
        )
        for fid in ids
    ]
    newest = max(by_week) if by_week else None
    return sorted(lines, key=_order(season, through_week, newest))
