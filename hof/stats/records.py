"""The records book: top-ten tables for teams and players, by game, season, and career."""

from __future__ import annotations

from dataclasses import dataclass

from hof.model.season import Game, Season
from hof.stats import franchises
from hof.stats.careers import Career
from hof.stats.league import League

TOP = 10


@dataclass(frozen=True)
class RecordEntry:
    value: float
    holder: str  # franchise name at the time, or player name
    detail: str
    year: int
    week: int | None  # None for season and career records
    playoff: bool
    franchise_id: str | None
    player_id: str | None


@dataclass(frozen=True)
class RecordTable:
    key: str
    title: str
    group: str
    entries: tuple[RecordEntry, ...]  # best first, at most TOP
    lowest_first: bool = False
    unit: str = "pts"


# (key, title, group, lowest_first, unit)
TABLES: tuple[tuple[str, str, str, bool, str], ...] = (
    ("team_game_high", "Most points, game", "Team, single game", False, "pts"),
    ("team_game_low", "Fewest points, game", "Team, single game", True, "pts"),
    ("blowout", "Biggest margin of victory", "Team, single game", False, "pts"),
    ("closest", "Closest game", "Team, single game", True, "pts"),
    ("loss_high", "Most points in a loss", "Team, single game", False, "pts"),
    ("win_low", "Fewest points in a win", "Team, single game", True, "pts"),
    ("bench_left_game", "Most points left on the bench, game", "Team, single game", False, "pts"),
    ("final_high", "Highest-scoring final", "Team, single game", False, "pts"),
    ("team_season_high", "Most points, season", "Team, season", False, "pts"),
    ("team_season_low", "Fewest points, season", "Team, season", True, "pts"),
    ("record_best", "Best record", "Team, season", False, "pct"),
    ("streak_win", "Longest win streak, season", "Team, season", False, "games"),
    ("streak_loss", "Longest loss streak, season", "Team, season", False, "games"),
    ("bench_left_season", "Most points left on the bench, season", "Team, season", False, "pts"),
    ("efficiency_season", "Best lineup efficiency, season", "Team, season", False, "pct"),
    ("player_game_high", "Most points as a starter, game", "Player, single game", False, "pts"),
    ("player_game_vor", "Highest value over replacement, game", "Player, single game", False, "vor"),
    ("player_season_high", "Most points as a starter, season", "Player, season", False, "pts"),
    ("player_season_vor", "Highest value over replacement, season", "Player, season", False, "vor"),
    ("player_season_starts", "Most starts, season", "Player, season", False, "starts"),
    ("career_points", "Most points as a starter, career", "Player, career", False, "pts"),
    ("career_vor", "Highest value over replacement, career", "Player, career", False, "vor"),
    ("career_starts", "Most starts, career", "Player, career", False, "starts"),
    ("career_titles", "Most titles as a starter, career", "Player, career", False, "titles"),
)


def _when(game: Game) -> str:
    label = f"{game.year} Week {game.week}"
    return f"{label} ({game.round_name})" if game.playoff and game.round_name else label


def _score(value: float | None) -> str:
    return f"{value or 0.0:.1f}"


def finished(season: Season) -> bool:
    """Season tables only use seasons whose bracket has been decided."""
    return season.complete or season.final is not None


def _game_entry(value: float, holder: str, detail: str, game: Game, franchise_id: str) -> RecordEntry:
    return RecordEntry(round(value, 1), holder, detail, game.year, game.week, game.playoff, franchise_id, None)


def _season_entry(value: float, holder: str, detail: str, year: int, franchise_id: str) -> RecordEntry:
    return RecordEntry(value, holder, detail, year, None, False, franchise_id, None)


def team_game_entries(league: League) -> dict[str, list[RecordEntry]]:
    out: dict[str, list[RecordEntry]] = {key: [] for key, *_ in TABLES}
    for season in league.seasons:
        for game in season.games():
            for own, opponent in ((game.home, game.away), (game.away, game.home)):
                name = league.name_in(own.franchise_id, season.year)
                other = league.name_in(opponent.franchise_id, season.year)
                score, other_score = own.score or 0.0, opponent.score or 0.0
                fid, when = own.franchise_id, _when(game)
                out["team_game_high"].append(_game_entry(score, name, f"vs {other}, {when}", game, fid))
                out["team_game_low"].append(_game_entry(score, name, f"vs {other}, {when}", game, fid))
                if score > other_score:
                    versus = f"{_score(score)}–{_score(other_score)}"
                    out["blowout"].append(_game_entry(game.margin, name, f"over {other} {versus}, {when}", game, fid))
                    out["closest"].append(_game_entry(game.margin, name, f"over {other} {versus}, {when}", game, fid))
                    out["win_low"].append(_game_entry(score, name, f"beat {other} {versus}, {when}", game, fid))
                elif score < other_score:
                    out["loss_high"].append(_game_entry(score, name, f"lost to {other} {_score(other_score)}–{_score(score)}, {when}", game, fid))
                if own.opt_pts is not None:
                    out["bench_left_game"].append(_game_entry(own.opt_pts - score, name, f"{_score(score)} of {_score(own.opt_pts)} possible, {when}", game, fid))
        final = season.final
        if final is not None and final.winner is not None and final.loser is not None:
            winner, loser = final.winner, final.loser
            out["final_high"].append(
                RecordEntry(
                    round((winner.score or 0.0) + (loser.score or 0.0), 1),
                    league.name_in(winner.franchise_id, season.year),
                    f"{_score(winner.score)}–{_score(loser.score)} over {league.name_in(loser.franchise_id, season.year)}, {season.year}",
                    season.year, final.week, True, winner.franchise_id, None,
                )
            )
    return out


def team_season_entries(league: League) -> dict[str, list[RecordEntry]]:
    out: dict[str, list[RecordEntry]] = {key: [] for key, *_ in TABLES}
    for season in league.seasons:
        if not finished(season):
            continue
        for fid in season.franchises:
            row = franchises.season_row(league, season, fid)
            if row is None or not (row.wins + row.losses + row.ties):
                continue
            games = franchises.meetings(league, season, fid)
            _, longest_win, longest_loss = franchises.streaks([m.result for m in games])
            score = opt = 0.0
            for game in season.games():
                lineup = game.lineup_of(fid)
                if lineup is not None and lineup.opt_pts is not None:
                    score += lineup.score or 0.0
                    opt += lineup.opt_pts

            record = f"{row.wins}-{row.losses}-{row.ties}"
            year = season.year
            out["team_season_high"].append(_season_entry(row.points_for, row.name, f"{year}, {record}", year, fid))
            out["team_season_low"].append(_season_entry(row.points_for, row.name, f"{year}, {record}", year, fid))
            pct = (row.wins + 0.5 * row.ties) / (row.wins + row.losses + row.ties)
            out["record_best"].append(_season_entry(round(pct, 3), row.name, f"{record}, {row.points_for:.1f} pts", year, fid))
            out["streak_win"].append(_season_entry(longest_win, row.name, f"{year}", year, fid))
            out["streak_loss"].append(_season_entry(longest_loss, row.name, f"{year}", year, fid))
            if opt:
                out["bench_left_season"].append(_season_entry(round(opt - score, 1), row.name, f"{year}", year, fid))
                out["efficiency_season"].append(_season_entry(round(score / opt, 3), row.name, f"{year}", year, fid))
    return out


def player_entries(league: League, careers: dict[str, Career]) -> dict[str, list[RecordEntry]]:
    out: dict[str, list[RecordEntry]] = {key: [] for key, *_ in TABLES}
    for season in league.seasons:
        rounds = {g.week: g.round_name for g in season.games() if g.playoff}
        for row in league.starts[season.year]:
            name = league.player_info(row.player_id).name
            franchise = league.name_in(row.franchise_id, season.year)
            when = f"{season.year} Week {row.week}"
            if row.playoff and rounds.get(row.week):
                when += f" ({rounds[row.week]})"
            out["player_game_high"].append(RecordEntry(row.points, name, f"{franchise}, {when}", season.year, row.week, row.playoff, row.franchise_id, row.player_id))
            out["player_game_vor"].append(RecordEntry(row.vor, name, f"{franchise}, {when}", season.year, row.week, row.playoff, row.franchise_id, row.player_id))
    for career in careers.values():
        for line in career.seasons:
            season = league.season(line.year)
            if not finished(season) or not line.starts:
                continue
            franchise = ", ".join(league.name_in(fid, line.year) for fid in line.franchise_ids) or "—"
            main = line.franchise_ids[0] if line.franchise_ids else None
            for key, value in (("player_season_high", line.points), ("player_season_vor", line.vor), ("player_season_starts", line.starts)):
                out[key].append(RecordEntry(value, career.name, f"{franchise}, {line.year}", line.year, None, False, main, career.player_id))
        span = f"{career.first_year}–{career.last_year}"
        for key, value in (("career_points", career.points), ("career_vor", career.vor), ("career_starts", career.starts), ("career_titles", career.titles)):
            out[key].append(RecordEntry(value, career.name, span, career.first_year, None, False, None, career.player_id))
    return out


def records_book(league: League, careers: dict[str, Career]) -> list[RecordTable]:
    pools: dict[str, list[RecordEntry]] = {key: [] for key, *_ in TABLES}
    for source in (team_game_entries(league), team_season_entries(league), player_entries(league, careers)):
        for key, entries in source.items():
            pools[key].extend(entries)
    tables: list[RecordTable] = []
    for key, title, group, lowest_first, unit in TABLES:
        sign = 1 if lowest_first else -1
        ordered = sorted(pools[key], key=lambda e: (sign * e.value, e.year, e.week or 0, e.holder))
        tables.append(RecordTable(key, title, group, tuple(ordered[:TOP]), lowest_first, unit))
    return tables


def entries_from_week(tables: list[RecordTable], year: int, week: int) -> list[tuple[RecordTable, RecordEntry]]:
    """Single-game top-ten entries set in the given week: the recap's "new records"."""
    found = []
    for table in tables:
        if table.group not in ("Team, single game", "Player, single game"):
            continue
        for entry in table.entries:
            if entry.year == year and entry.week == week:
                found.append((table, entry))
    return found
