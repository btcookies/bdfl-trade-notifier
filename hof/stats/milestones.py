"""Facts for the weekly recap: the week's best, new records, milestones, series firsts, standings."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from hof.model.season import Season
from hof.stats import franchises
from hof.stats.careers import WeekKey
from hof.stats.league import League
from hof.stats.records import RecordTable, entries_from_week

PLAYOFF_SPOTS = 6
POINT_STEP = 500
START_STEP = 100
SERIES_GAP_SEASONS = 2


@dataclass(frozen=True)
class RecapFacts:
    year: int
    week: int
    playoff: bool
    high_score: tuple[str, float] | None  # (franchise name, score)
    top_starter: tuple[str, str, float, float] | None  # (player, franchise, points, vor)
    new_records: tuple[str, ...]
    milestones: tuple[str, ...]
    series_firsts: tuple[str, ...]
    playoff_picture: tuple[str, ...]  # regular-season weeks only
    bracket: tuple[str, ...]  # playoff weeks only


@dataclass(frozen=True)
class SeasonAwards:
    """The season wrap's numbers; every field is None when the season has no counted games."""

    year: int
    top_scorer: tuple[str, str, float] | None  # (player, franchise, points)
    best_vor: tuple[str, str, float] | None  # (player, franchise, vor)
    best_manager: tuple[str, float] | None  # (franchise, lineup efficiency)
    most_bench_left: tuple[str, float] | None  # (franchise, points left on the bench)
    champion: tuple[str, str, float, int | None] | None  # (name, record, points for, all-time rank of that season's points)


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _format(value: float, unit: str) -> str:
    if unit in ("starts", "games", "titles"):
        return f"{int(value)} {unit}"
    if unit == "wins":
        return f"{value:+.1f} wins"
    if unit == "pct":
        return f"{value:.3f}"
    return f"{value:.1f} {unit}"


def new_records(tables: list[RecordTable], year: int, week: int) -> tuple[str, ...]:
    lines = []
    for table, entry in entries_from_week(tables, year, week):
        rank = table.entries.index(entry) + 1
        lines.append(f"{entry.holder} — {_format(entry.value, table.unit)} ({table.title}, #{rank})")
    return tuple(lines)


def week_milestones(league: League, key: WeekKey, point_step: int, start_step: int) -> tuple[str, ...]:
    points: dict[str, float] = defaultdict(float)
    starts: dict[str, int] = defaultdict(int)
    lines: list[str] = []
    for row in league.all_starts():
        if (row.year, row.week) >= key:
            continue
        points[row.player_id] += row.points
        starts[row.player_id] += 1
    this_week = [r for r in league.starts.get(key[0], []) if r.week == key[1]]
    for row in sorted(this_week, key=lambda r: (league.player_info(r.player_id).name, r.player_id)):
        name = league.player_info(row.player_id).name
        franchise = league.name_in(row.franchise_id, row.year)
        before_points, after_points = points[row.player_id], points[row.player_id] + row.points
        if int(before_points // point_step) < int(after_points // point_step):
            lines.append(f"{name} passed {int(after_points // point_step) * point_step} career points as a starter ({franchise})")
        after_starts = starts[row.player_id] + 1
        if after_starts % start_step == 0:
            lines.append(f"{name} made career start number {after_starts} ({franchise})")
    return tuple(lines)


def series_firsts(league: League, season: Season, week: int) -> tuple[str, ...]:
    lines: list[str] = []
    for game in season.games():
        if game.week != week or game.winner is None or game.loser is None:
            continue
        winner, loser = game.winner.franchise_id, game.loser.franchise_id
        previous = [
            m
            for s in league.seasons
            if s.year <= season.year
            for m in franchises.meetings(league, s, winner)
            if m.opponent_id == loser and (s.year, m.week) < (season.year, week)
        ]
        wins = [m for m in previous if m.result == "W"]
        record = franchises.series(league, winner, previous + [m for m in franchises.meetings(league, season, winner) if m.opponent_id == loser and m.week == week])[0]
        series_text = f"series now {record.wins}-{record.losses}-{record.ties}"
        winner_name, loser_name = league.name_in(winner, season.year), league.name_in(loser, season.year)
        if not wins:
            lines.append(f"{winner_name} beat {loser_name} for the first time ever ({series_text})")
        elif wins[-1].year <= season.year - SERIES_GAP_SEASONS:
            lines.append(f"{winner_name} beat {loser_name} for the first time since {wins[-1].year} ({series_text})")
    return tuple(lines)


def playoff_picture(league: League, season: Season) -> tuple[str, ...]:
    rows = [row for fid in season.franchises if (row := franchises.season_row(league, season, fid)) is not None]
    if season.standings:
        order = {s.franchise_id: i for i, s in enumerate(season.standings)}
        ids = {league.name_in(fid, season.year): fid for fid in season.franchises}
        rows.sort(key=lambda r: order.get(ids.get(r.name, ""), 99))
    else:
        rows.sort(key=lambda r: (-(r.wins + 0.5 * r.ties), -r.points_for, r.name))
    lines = [f"{i}. {row.name} {row.wins}-{row.losses}-{row.ties}" for i, row in enumerate(rows[:PLAYOFF_SPOTS], start=1)]
    if len(rows) > PLAYOFF_SPOTS:
        sixth = rows[PLAYOFF_SPOTS - 1]
        close = [f"{row.name} ({row.wins}-{row.losses}-{row.ties})" for row in rows[PLAYOFF_SPOTS:] if row.wins >= sixth.wins - 1]
        if close:
            lines.append("Within a game: " + ", ".join(close))
    return tuple(lines)


def bracket_summary(league: League, season: Season, week: int) -> tuple[str, ...]:
    lines: list[str] = []
    for game in season.games():
        if game.week != week or not game.playoff:
            continue
        winner, loser = game.winner or game.home, game.loser or game.away
        lines.append(
            f"{game.round_name}: {league.name_in(winner.franchise_id, season.year)} {winner.score or 0.0:.1f}, "
            f"{league.name_in(loser.franchise_id, season.year)} {loser.score or 0.0:.1f}"
        )
    upcoming = [g for g in season.bracket if g.week > week]
    if upcoming:
        next_week = min(g.week for g in upcoming)
        for game in upcoming:
            if game.week == next_week and game.home_id and game.away_id:
                lines.append(f"Next: {season.round_name(game.round_index)}, {league.name_in(game.home_id, season.year)} vs {league.name_in(game.away_id, season.year)}")
    return tuple(lines)


def season_awards(league: League, tables: list[RecordTable], year: int) -> SeasonAwards:
    season = league.season(year)
    points: dict[str, float] = defaultdict(float)
    vor: dict[str, float] = defaultdict(float)
    franchise_of: dict[str, str] = {}
    for row in league.starts.get(year, []):
        points[row.player_id] += row.points
        vor[row.player_id] += row.vor
        franchise_of[row.player_id] = row.franchise_id

    def player_award(totals: dict[str, float]) -> tuple[str, str, float] | None:
        if not totals:
            return None
        best = max(totals, key=lambda pid: (totals[pid], league.player_info(pid).name))
        return league.player_info(best).name, league.name_in(franchise_of[best], year), round(totals[best], 1)

    scored: dict[str, float] = defaultdict(float)
    optimal: dict[str, float] = defaultdict(float)
    for game in season.games():
        for lineup in (game.home, game.away):
            if lineup.opt_pts is not None:
                scored[lineup.franchise_id] += lineup.score or 0.0
                optimal[lineup.franchise_id] += lineup.opt_pts
    manager = bench = None
    if optimal:
        best = max(optimal, key=lambda fid: (scored[fid] / optimal[fid], scored[fid]))
        manager = (league.name_in(best, year), round(scored[best] / optimal[best], 3))
        most = max(optimal, key=lambda fid: (optimal[fid] - scored[fid], fid))
        bench = (league.name_in(most, year), round(optimal[most] - scored[most], 1))
    champion = None
    if season.champion_id is not None:
        row = franchises.season_row(league, season, season.champion_id)
        if row is not None:
            table = next(t for t in tables if t.key == "team_season_high")
            rank = next((i + 1 for i, e in enumerate(table.entries) if e.year == year and e.franchise_id == season.champion_id), None)
            champion = (row.name, f"{row.wins}-{row.losses}-{row.ties}", row.points_for, rank)
    return SeasonAwards(year, player_award(points), player_award(vor), manager, bench, champion)


def recap_facts(
    league: League,
    tables: list[RecordTable],
    key: WeekKey,
    point_step: int = POINT_STEP,
    start_step: int = START_STEP,
) -> RecapFacts:
    year, week = key
    season = league.season(year)
    games = [g for g in season.games() if g.week == week]
    playoff = week > season.last_regular_season_week
    high: tuple[str, float] | None = None
    for game in games:
        for lineup in (game.home, game.away):
            if high is None or (lineup.score or 0.0) > high[1]:
                high = (league.name_in(lineup.franchise_id, year), lineup.score or 0.0)
    top: tuple[str, str, float, float] | None = None
    for row in league.starts.get(year, []):
        if row.week == week and (top is None or (row.vor, row.points) > (top[3], top[2])):
            top = (league.player_info(row.player_id).name, league.name_in(row.franchise_id, year), row.points, row.vor)
    return RecapFacts(
        year=year,
        week=week,
        playoff=playoff,
        high_score=high,
        top_starter=top,
        new_records=new_records(tables, year, week),
        milestones=week_milestones(league, key, point_step, start_step),
        series_firsts=series_firsts(league, season, week),
        playoff_picture=() if playoff else playoff_picture(league, season),
        bracket=bracket_summary(league, season, week) if playoff else (),
    )
