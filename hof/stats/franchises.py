"""Franchise histories: season rows and finishes, era and all-time totals, streaks, head-to-head."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from hof.model.season import Lineup, Season
from hof.stats import allplay
from hof.stats.league import Era, League


@dataclass(frozen=True)
class Totals:
    games: int
    wins: int
    losses: int
    ties: int
    points_for: float
    points_against: float
    playoff_apps: int
    playoff_wins: int
    playoff_losses: int
    titles: int
    allplay_wins: int = 0
    allplay_losses: int = 0
    allplay_ties: int = 0
    expected_wins: float = 0.0  # two decimals

    @property
    def win_pct(self) -> float:
        return (self.wins + 0.5 * self.ties) / self.games if self.games else 0.0

    @property
    def record(self) -> str:
        return f"{self.wins}-{self.losses}-{self.ties}"

    @property
    def allplay_record(self) -> str:
        return f"{self.allplay_wins}-{self.allplay_losses}-{self.allplay_ties}"

    @property
    def allplay_pct(self) -> float:
        total = self.allplay_wins + self.allplay_losses + self.allplay_ties
        return (self.allplay_wins + 0.5 * self.allplay_ties) / total if total else 0.0

    @property
    def luck(self) -> float:
        return round(self.wins + 0.5 * self.ties - self.expected_wins, 1)


@dataclass(frozen=True)
class SeasonRow:
    year: int
    name: str  # the name used that season
    wins: int
    losses: int
    ties: int
    division_record: str
    points_for: float
    points_against: float
    seed: int | None
    playoff_wins: int
    playoff_losses: int
    finish: str
    title: bool
    in_progress: bool
    top_starter: tuple[str, str, float, float] | None  # (player id, name, points, vor)
    allplay: tuple[int, int, int] = (0, 0, 0)
    expected_wins: float = 0.0
    luck: float = 0.0


@dataclass(frozen=True)
class EraSummary:
    era: Era
    rows: tuple[SeasonRow, ...]  # newest first
    totals: Totals


@dataclass(frozen=True)
class Meeting:
    """One counted game from one franchise's point of view."""

    year: int
    week: int
    playoff: bool
    round_name: str | None
    own_name: str
    opponent_id: str
    opponent_name: str
    own_score: float
    opponent_score: float
    result: str  # W, L, or T


@dataclass(frozen=True)
class Series:
    opponent_id: str
    opponent_name: str  # current name
    wins: int
    losses: int
    ties: int
    regular: tuple[int, int, int]
    playoff: tuple[int, int, int]
    points_for: float
    points_against: float
    avg_margin: float
    streak: str
    last: Meeting | None
    meetings: tuple[Meeting, ...]  # oldest first


@dataclass(frozen=True)
class TopStarter:
    player_id: str
    name: str
    position: str
    first_year: int
    last_year: int
    starts: int
    points: float
    vor: float


@dataclass(frozen=True)
class FranchiseHistory:
    id: str
    name: str  # current name
    eras: tuple[EraSummary, ...]  # newest first
    totals: Totals
    streak: str
    longest_win_streak: int
    longest_loss_streak: int
    best_season: SeasonRow | None
    worst_season: SeasonRow | None
    series: tuple[Series, ...]  # by opponent's current name
    top_starters: tuple[TopStarter, ...]  # by vor, descending
    playoff_games: tuple[Meeting, ...]  # newest first


def _result(own: Lineup, opponent: Lineup) -> str:
    own_score, opponent_score = own.score or 0.0, opponent.score or 0.0
    if own_score == opponent_score:
        return "T"
    return "W" if own_score > opponent_score else "L"


def meetings(league: League, season: Season, franchise_id: str) -> list[Meeting]:
    rows: list[Meeting] = []
    for game in season.games():
        own, opponent = game.lineup_of(franchise_id), game.opponent_of(franchise_id)
        if own is None or opponent is None:
            continue
        rows.append(
            Meeting(
                year=season.year,
                week=game.week,
                playoff=game.playoff,
                round_name=game.round_name,
                own_name=league.name_in(franchise_id, season.year),
                opponent_id=opponent.franchise_id,
                opponent_name=league.name_in(opponent.franchise_id, season.year),
                own_score=own.score or 0.0,
                opponent_score=opponent.score or 0.0,
                result=_result(own, opponent),
            )
        )
    return rows


def _seed(season: Season, franchise_id: str) -> int | None:
    for game in season.bracket:
        if game.home_id == franchise_id and game.home_seed is not None:
            return game.home_seed
        if game.away_id == franchise_id and game.away_seed is not None:
            return game.away_seed
    return None


def _finish(season: Season, franchise_id: str, playoff_meetings: list[Meeting], seed: int | None) -> tuple[str, bool]:
    """(finish label, in_progress)."""
    if not season.complete and season.final is None:
        return "In progress", True
    if season.champion_id == franchise_id:
        return "Champion", False
    final = season.final
    if final is not None and final.loser is not None and final.loser.franchise_id == franchise_id:
        return "Runner-up", False
    if playoff_meetings:
        return f"Lost {playoff_meetings[-1].round_name or 'playoff game'}", False
    if seed is not None:
        return "Playoffs", False
    return "Missed playoffs", False


def _top_starter(league: League, season: Season, franchise_id: str) -> tuple[str, str, float, float] | None:
    points: dict[str, float] = defaultdict(float)
    vor: dict[str, float] = defaultdict(float)
    for row in league.starts[season.year]:
        if row.franchise_id == franchise_id:
            points[row.player_id] += row.points
            vor[row.player_id] += row.vor
    if not vor:
        return None
    best = max(vor, key=lambda pid: (vor[pid], points[pid]))
    return best, season.player(best).name, round(points[best], 1), round(vor[best], 1)


def season_row(league: League, season: Season, franchise_id: str) -> SeasonRow | None:
    if franchise_id not in season.franchises:
        return None
    games = meetings(league, season, franchise_id)
    regular = [m for m in games if not m.playoff]
    playoff = [m for m in games if m.playoff]
    seed = _seed(season, franchise_id)
    finish, in_progress = _finish(season, franchise_id, playoff, seed)
    standing = next((s for s in season.standings if s.franchise_id == franchise_id), None)
    # standings() lists every franchise in the season, so this lookup always succeeds.
    line = next(s for s in allplay.standings(league, season, None) if s.franchise_id == franchise_id)
    return SeasonRow(
        year=season.year,
        name=league.name_in(franchise_id, season.year),
        wins=sum(1 for m in regular if m.result == "W"),
        losses=sum(1 for m in regular if m.result == "L"),
        ties=sum(1 for m in regular if m.result == "T"),
        division_record=standing.division_record if standing else "",
        points_for=round(sum(m.own_score for m in regular), 1),
        points_against=round(sum(m.opponent_score for m in regular), 1),
        seed=seed,
        playoff_wins=sum(1 for m in playoff if m.result == "W"),
        playoff_losses=sum(1 for m in playoff if m.result == "L"),
        finish=finish,
        title=season.champion_id == franchise_id,
        in_progress=in_progress,
        top_starter=_top_starter(league, season, franchise_id),
        allplay=line.allplay,
        expected_wins=line.expected_wins,
        luck=line.luck,
    )


def season_rows(league: League, franchise_id: str) -> list[SeasonRow]:
    """Oldest first."""
    rows = (season_row(league, season, franchise_id) for season in league.seasons)
    return [row for row in rows if row is not None]


def totals(rows: list[SeasonRow] | tuple[SeasonRow, ...]) -> Totals:
    wins, losses, ties = (sum(getattr(r, key) for r in rows) for key in ("wins", "losses", "ties"))
    return Totals(
        games=wins + losses + ties,
        wins=wins,
        losses=losses,
        ties=ties,
        points_for=round(sum(r.points_for for r in rows), 1),
        points_against=round(sum(r.points_against for r in rows), 1),
        playoff_apps=sum(1 for r in rows if r.seed is not None),
        playoff_wins=sum(r.playoff_wins for r in rows),
        playoff_losses=sum(r.playoff_losses for r in rows),
        titles=sum(1 for r in rows if r.title),
        allplay_wins=sum(r.allplay[0] for r in rows),
        allplay_losses=sum(r.allplay[1] for r in rows),
        allplay_ties=sum(r.allplay[2] for r in rows),
        expected_wins=round(sum(r.expected_wins for r in rows), 2),
    )


def streaks(results: list[str]) -> tuple[str, int, int]:
    """(current streak like W3, longest win streak, longest loss streak) over W/L/T results in order."""
    longest = {"W": 0, "L": 0}
    run_kind, run_length = "", 0
    for result in results:
        if result == run_kind:
            run_length += 1
        else:
            run_kind, run_length = result, 1
        if result in longest:
            longest[result] = max(longest[result], run_length)
    current = f"{run_kind}{run_length}" if run_kind else ""
    return current, longest["W"], longest["L"]


def series(league: League, franchise_id: str, all_meetings: list[Meeting]) -> list[Series]:
    by_opponent: dict[str, list[Meeting]] = defaultdict(list)
    for meeting in all_meetings:
        by_opponent[meeting.opponent_id].append(meeting)
    out: list[Series] = []
    for opponent_id, games in by_opponent.items():

        def split(rows: list[Meeting]) -> tuple[int, int, int]:
            return (
                sum(1 for m in rows if m.result == "W"),
                sum(1 for m in rows if m.result == "L"),
                sum(1 for m in rows if m.result == "T"),
            )

        wins, losses, ties = split(games)
        out.append(
            Series(
                opponent_id=opponent_id,
                opponent_name=league.current_name(opponent_id),
                wins=wins,
                losses=losses,
                ties=ties,
                regular=split([m for m in games if not m.playoff]),
                playoff=split([m for m in games if m.playoff]),
                points_for=round(sum(m.own_score for m in games), 1),
                points_against=round(sum(m.opponent_score for m in games), 1),
                avg_margin=round(sum(m.own_score - m.opponent_score for m in games) / len(games), 1),
                streak=streaks([m.result for m in games])[0],
                last=games[-1],
                meetings=tuple(games),
            )
        )
    return sorted(out, key=lambda s: s.opponent_name.casefold())


def top_starters(league: League, franchise_id: str) -> list[TopStarter]:
    stats: dict[str, dict] = {}
    for row in league.all_starts():
        if row.franchise_id != franchise_id:
            continue
        entry = stats.setdefault(row.player_id, {"first": row.year, "last": row.year, "starts": 0, "points": 0.0, "vor": 0.0})
        entry["first"] = min(entry["first"], row.year)
        entry["last"] = max(entry["last"], row.year)
        entry["starts"] += 1
        entry["points"] += row.points
        entry["vor"] += row.vor
    out = [
        TopStarter(pid, league.player_info(pid).name, league.player_info(pid).position, e["first"], e["last"], e["starts"], round(e["points"], 1), round(e["vor"], 1))
        for pid, e in stats.items()
    ]
    return sorted(out, key=lambda t: (-t.vor, -t.points, t.name))


def franchise_history(league: League, franchise_id: str) -> FranchiseHistory:
    rows = season_rows(league, franchise_id)
    eras: list[EraSummary] = []
    for era in reversed(league.eras(franchise_id)):
        era_rows = tuple(sorted((r for r in rows if era.first_year <= r.year <= era.last_year), key=lambda r: -r.year))
        eras.append(EraSummary(era, era_rows, totals(era_rows)))
    all_meetings = [m for season in league.seasons for m in meetings(league, season, franchise_id)]
    current, longest_win, longest_loss = streaks([m.result for m in all_meetings])
    complete_rows = [r for r in rows if not r.in_progress and (r.wins + r.losses + r.ties)]
    return FranchiseHistory(
        id=franchise_id,
        name=league.current_name(franchise_id),
        eras=tuple(eras),
        totals=totals(rows),
        streak=current,
        longest_win_streak=longest_win,
        longest_loss_streak=longest_loss,
        best_season=max(complete_rows, key=_season_rank, default=None),
        worst_season=min(complete_rows, key=_season_rank, default=None),
        series=tuple(series(league, franchise_id, all_meetings)),
        top_starters=tuple(top_starters(league, franchise_id)),
        playoff_games=tuple(sorted((m for m in all_meetings if m.playoff), key=lambda m: (-m.year, -m.week))),
    )


def _season_rank(row: SeasonRow) -> tuple[float, float]:
    games = row.wins + row.losses + row.ties
    return ((row.wins + 0.5 * row.ties) / games if games else 0.0, row.points_for)


def all_franchises(league: League) -> dict[str, FranchiseHistory]:
    return {fid: franchise_history(league, fid) for fid in league.franchise_ids()}
