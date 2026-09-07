"""One season: franchises, weeks of lineups, counted games, bracket, standings, draft."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any

from bdfl.models import as_list, split_assets
from hof.model.players import PlayerInfo
from hof.model.transactions import TransactionLog

log = logging.getLogger(__name__)

ROUND_NAMES = ("Final", "Semifinal", "Quarterfinal", "Round of 16")
RESULTS = {"W", "L", "T"}


def normalize_name(name: str) -> str:
    """Casefold and collapse whitespace so era boundaries ignore cosmetic renames."""
    return re.sub(r"\s+", " ", name).strip().casefold()


def float_or_none(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def int_or_none(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class Franchise:
    id: str
    name: str
    division: str = ""


@dataclass(frozen=True)
class Lineup:
    franchise_id: str
    starters: tuple[str, ...]
    nonstarters: tuple[str, ...]
    scores: dict[str, float] = field(compare=False)  # only players MFL scored
    score: float | None = None  # franchise total; None until played
    opt_pts: float | None = None
    result: str | None = None  # W, L, T, or None

    @property
    def played(self) -> bool:
        return self.score is not None and bool(self.starters)

    def points(self, player_id: str) -> float:
        return self.scores.get(player_id, 0.0)


@dataclass(frozen=True)
class Week:
    number: int
    lineups: dict[str, Lineup]  # every lineup MFL listed, by franchise id
    matchups: tuple[tuple[str, str], ...]  # (home id, away id)


@dataclass(frozen=True)
class BracketGame:
    week: int
    game_id: str
    round_index: int  # 0 = first round
    home_id: str | None
    away_id: str | None
    home_seed: int | None
    away_seed: int | None


@dataclass(frozen=True)
class BracketInfo:
    """The playoff bracket's declared shape, from playoffBrackets.json.

    This exists independently of how many rounds have actually been played, so it's the
    reliable way to know a bracket's total round count -- unlike counting round_index values in
    the BracketGame list, which only reflects whatever rounds MFL has posted results for so far.
    """

    teams_involved: int | None


def bracket_round_count(teams_involved: int) -> int:
    """Single-elimination round count for a bracket of this many teams.

    Byes fill any gap to the next power of two, e.g. 6 teams (two byes) still needs 3 rounds,
    the same as a full 8-team bracket -- only the first round has fewer games.
    """
    return math.ceil(math.log2(teams_involved)) if teams_involved > 1 else 0


@dataclass(frozen=True)
class Standing:
    franchise_id: str
    wins: int
    losses: int
    ties: int
    points_for: float
    points_against: float
    division_record: str
    streak: str


@dataclass(frozen=True)
class DraftPick:
    round: int
    pick: int
    franchise_id: str
    player_id: str
    timestamp: int
    comments: str = ""


@dataclass(frozen=True)
class Game:
    year: int
    week: int
    home: Lineup
    away: Lineup
    playoff: bool
    round_name: str | None = None

    @property
    def winner(self) -> Lineup | None:
        home, away = self.home.score or 0.0, self.away.score or 0.0
        if home == away:
            return None
        return self.home if home > away else self.away

    @property
    def loser(self) -> Lineup | None:
        winner = self.winner
        if winner is None:
            return None
        return self.away if winner is self.home else self.home

    @property
    def tie(self) -> bool:
        return self.winner is None

    @property
    def margin(self) -> float:
        return round(abs((self.home.score or 0.0) - (self.away.score or 0.0)), 1)

    def lineup_of(self, franchise_id: str) -> Lineup | None:
        if self.home.franchise_id == franchise_id:
            return self.home
        if self.away.franchise_id == franchise_id:
            return self.away
        return None

    def opponent_of(self, franchise_id: str) -> Lineup | None:
        if self.home.franchise_id == franchise_id:
            return self.away
        if self.away.franchise_id == franchise_id:
            return self.home
        return None


@dataclass(frozen=True)
class Season:
    year: int
    league_id: str
    name: str
    complete: bool
    franchises: dict[str, Franchise]
    starter_minimums: dict[str, int]
    start_week: int
    end_week: int
    last_regular_season_week: int
    weeks: dict[int, Week]
    bracket: tuple[BracketGame, ...]
    standings: tuple[Standing, ...]  # in MFL's standings order
    draft: tuple[DraftPick, ...]
    round1_order: tuple[str, ...]
    transactions: TransactionLog
    players: dict[str, PlayerInfo]
    bracket_info: BracketInfo | None = None

    def player(self, player_id: str) -> PlayerInfo:
        return self.players.get(player_id) or PlayerInfo.unknown(player_id)

    def franchise_name(self, franchise_id: str) -> str:
        franchise = self.franchises.get(franchise_id)
        return franchise.name if franchise else f"Franchise {franchise_id}"

    @property
    def bracket_rounds(self) -> int:
        """The bracket's total round count.

        Anchored to the bracket's declared size (bracket_info) when known, rather than to how
        many rounds happen to be in the export -- a mid-playoffs season only has results for the
        rounds played so far, and counting those would name the latest available round "Final"
        and crown a champion before the bracket is actually finished.
        """
        if self.bracket_info is not None and self.bracket_info.teams_involved:
            return bracket_round_count(self.bracket_info.teams_involved)
        return max((g.round_index for g in self.bracket), default=-1) + 1

    def round_name(self, round_index: int) -> str:
        from_end = self.bracket_rounds - 1 - round_index
        if 0 <= from_end < len(ROUND_NAMES):
            return ROUND_NAMES[from_end]
        return f"Round {round_index + 1}"

    def playoff_weeks(self) -> set[int]:
        return {g.week for g in self.bracket}

    def games(self) -> list[Game]:
        """Counted games in week order: every regular-season matchup, then bracket games only."""
        games: list[Game] = []
        for number in sorted(self.weeks):
            week = self.weeks[number]
            if number <= self.last_regular_season_week:
                for home_id, away_id in week.matchups:
                    game = self._game(week, home_id, away_id, playoff=False)
                    if game is not None:
                        games.append(game)
                continue
            for bracket_game in self.bracket:
                if bracket_game.week != number or not bracket_game.home_id or not bracket_game.away_id:
                    continue
                pair = {bracket_game.home_id, bracket_game.away_id}
                matchup = next((m for m in week.matchups if set(m) == pair), None)
                if matchup is None:
                    # weeklyResults didn't pair them as a matchup (e.g. both listed as
                    # franchise-only entries); both lineups are still in week.lineups, so build
                    # the game directly from the bracket's own home/away rather than dropping it.
                    log.debug("%s week %s: bracket game %s has no matchup entry, using bracket home/away", self.year, number, bracket_game.game_id)
                    home_id, away_id = bracket_game.home_id, bracket_game.away_id
                else:
                    home_id, away_id = matchup
                game = self._game(week, home_id, away_id, playoff=True, round_name=self.round_name(bracket_game.round_index))
                if game is not None:
                    games.append(game)
        return games

    def _game(self, week: Week, home_id: str, away_id: str, playoff: bool, round_name: str | None = None) -> Game | None:
        home, away = week.lineups.get(home_id), week.lineups.get(away_id)
        if home is None or away is None or not home.played or not away.played:
            return None
        return Game(self.year, week.number, home, away, playoff, round_name)

    @property
    def final(self) -> Game | None:
        finals = [g for g in self.games() if g.playoff and g.round_name == "Final"]
        return finals[-1] if finals else None

    @property
    def champion_id(self) -> str | None:
        final = self.final
        if final is None or final.winner is None:
            return None
        return final.winner.franchise_id


@dataclass(frozen=True)
class LeagueSettings:
    name: str
    franchises: dict[str, Franchise]
    starter_minimums: dict[str, int]
    start_week: int
    end_week: int
    last_regular_season_week: int


def parse_league(body: dict[str, Any]) -> LeagueSettings:
    league = body.get("league") or {}
    franchises = {
        str(f["id"]): Franchise(str(f["id"]), str(f.get("name") or "").strip() or f"Franchise {f['id']}", str(f.get("division") or ""))
        for f in as_list((league.get("franchises") or {}).get("franchise"))
        if "id" in f
    }
    minimums: dict[str, int] = {}
    for position in as_list((league.get("starters") or {}).get("position")):
        name = str(position.get("name") or "").strip()
        limit = str(position.get("limit") or "1").split("-")[0]
        if name and limit.isdigit():
            minimums[name] = int(limit)
    return LeagueSettings(
        name=str(league.get("name") or "").strip(),
        franchises=franchises,
        starter_minimums=minimums,
        start_week=int_or_none(league.get("startWeek")) or 1,
        end_week=int_or_none(league.get("endWeek")) or 17,
        last_regular_season_week=int_or_none(league.get("lastRegularSeasonWeek")) or 13,
    )


def _lineup(raw: dict[str, Any]) -> Lineup:
    scores: dict[str, float] = {}
    for player in as_list(raw.get("player")):
        score = float_or_none(player.get("score"))
        if "id" in player and score is not None:
            scores[str(player["id"])] = score
    result = str(raw.get("result") or "").strip().upper()
    return Lineup(
        franchise_id=str(raw["id"]),
        starters=split_assets(raw.get("starters")),
        nonstarters=split_assets(raw.get("nonstarters")),
        scores=scores,
        score=float_or_none(raw.get("score")),
        opt_pts=float_or_none(raw.get("opt_pts")),
        result=result if result in RESULTS else None,
    )


def parse_week(body: dict[str, Any], number: int) -> Week:
    results = body.get("weeklyResults") or {}
    lineups: dict[str, Lineup] = {}
    matchups: list[tuple[str, str]] = []
    for matchup in as_list(results.get("matchup")):
        sides = [f for f in as_list(matchup.get("franchise")) if "id" in f]
        if len(sides) != 2:
            continue
        home, away = (sides[1], sides[0]) if str(sides[1].get("isHome")) == "1" else (sides[0], sides[1])
        for side in (home, away):
            lineups[str(side["id"])] = _lineup(side)
        matchups.append((str(home["id"]), str(away["id"])))
    for raw in as_list(results.get("franchise")):
        if "id" in raw and str(raw["id"]) not in lineups:
            lineups[str(raw["id"])] = _lineup(raw)
    return Week(number=number, lineups=lineups, matchups=tuple(matchups))


def parse_bracket(body: dict[str, Any]) -> tuple[BracketGame, ...]:
    games: list[BracketGame] = []
    rounds = as_list((body.get("playoffBracket") or {}).get("playoffRound"))
    rounds = sorted(rounds, key=lambda r: int_or_none(r.get("week")) or 0)
    for round_index, round_ in enumerate(rounds):
        week = int_or_none(round_.get("week"))
        if week is None:
            continue
        for game in as_list(round_.get("playoffGame")):
            home, away = game.get("home") or {}, game.get("away") or {}
            games.append(
                BracketGame(
                    week=week,
                    game_id=str(game.get("game_id") or len(games) + 1),
                    round_index=round_index,
                    home_id=str(home["franchise_id"]) if home.get("franchise_id") else None,
                    away_id=str(away["franchise_id"]) if away.get("franchise_id") else None,
                    home_seed=int_or_none(home.get("seed")),
                    away_seed=int_or_none(away.get("seed")),
                )
            )
    return tuple(games)


def parse_bracket_info(body: dict[str, Any]) -> BracketInfo | None:
    """The bracket's declared shape from playoffBrackets.json (the league's list of brackets,
    not to be confused with playoffBracket-<id>.json's per-bracket game results).

    A league with a consolation bracket alongside the championship one would list more than one
    entry here; this takes the first that declares a team count, since only the championship
    bracket's round count and champion matter to Season.
    """
    for entry in as_list((body.get("playoffBrackets") or {}).get("playoffBracket")):
        teams = int_or_none(entry.get("teamsInvolved"))
        if teams is not None:
            return BracketInfo(teams_involved=teams)
    return None


def parse_standings(body: dict[str, Any]) -> tuple[Standing, ...]:
    standings: list[Standing] = []
    for raw in as_list((body.get("leagueStandings") or {}).get("franchise")):
        if "id" not in raw:
            continue
        record = str(raw.get("h2hwlt") or "0-0-0").split("-")
        wins = int_or_none(raw.get("h2hw"))
        losses = int_or_none(raw.get("h2hl"))
        ties = int_or_none(raw.get("h2ht"))
        standings.append(
            Standing(
                franchise_id=str(raw["id"]),
                wins=wins if wins is not None else int_or_none(record[0]) or 0,
                losses=losses if losses is not None else (int_or_none(record[1]) if len(record) > 1 else 0) or 0,
                ties=ties if ties is not None else (int_or_none(record[2]) if len(record) > 2 else 0) or 0,
                points_for=float_or_none(raw.get("pf")) or 0.0,
                points_against=float_or_none(raw.get("pa")) or 0.0,
                division_record=str(raw.get("divwlt") or ""),
                streak=str(raw.get("strk") or ""),
            )
        )
    return tuple(standings)


def parse_draft(body: dict[str, Any]) -> tuple[tuple[DraftPick, ...], tuple[str, ...]]:
    picks: list[DraftPick] = []
    order: tuple[str, ...] = ()
    for unit in as_list((body.get("draftResults") or {}).get("draftUnit")):
        if not order:
            order = split_assets(unit.get("round1DraftOrder"))
        for raw in as_list(unit.get("draftPick")):
            round_, pick = int_or_none(raw.get("round")), int_or_none(raw.get("pick"))
            if round_ is None or pick is None or not raw.get("player") or not raw.get("franchise"):
                continue
            picks.append(
                DraftPick(
                    round=round_,
                    pick=pick,
                    franchise_id=str(raw["franchise"]),
                    player_id=str(raw["player"]),
                    timestamp=int_or_none(raw.get("timestamp")) or 0,
                    comments=str(raw.get("comments") or "").strip(),
                )
            )
    picks.sort(key=lambda p: (p.round, p.pick))
    return tuple(picks), order
