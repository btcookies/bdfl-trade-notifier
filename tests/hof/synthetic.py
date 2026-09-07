"""Builders for small synthetic seasons used by the stats tests."""

from __future__ import annotations

from dataclasses import replace

from hof.model.players import PlayerInfo
from hof.model.season import BracketGame, Franchise, Lineup, Season, Week
from hof.model.transactions import TransactionLog


def lineup(
    franchise_id: str,
    starters: dict[str, float | None],
    bench: dict[str, float | None] | None = None,
    opt_pts: float | None = None,
) -> Lineup:
    """A played lineup. A None score means MFL listed the player without a score."""
    bench = bench or {}
    scores = {pid: s for pid, s in {**starters, **bench}.items() if s is not None}
    total = round(sum(starters.get(pid) or 0.0 for pid in starters), 1)
    return Lineup(
        franchise_id=franchise_id,
        starters=tuple(starters),
        nonstarters=tuple(bench),
        scores=scores,
        score=total,
        opt_pts=total if opt_pts is None else opt_pts,
        result=None,
    )


def build_season(
    year: int,
    players: dict[str, tuple[str, str]],
    weeks: dict[int, list[tuple[Lineup, Lineup]]],
    last_regular_season_week: int,
    franchises: tuple[str, ...] = ("0001", "0002", "0003", "0004"),
    bracket: tuple[BracketGame, ...] = (),
    starter_minimums: dict[str, int] | None = None,
    complete: bool = True,
    transactions: TransactionLog | None = None,
    names: dict[str, str] | None = None,
) -> Season:
    """weeks maps week number to (home, away) lineup pairs; results are filled from scores.

    players maps id to (name, position). names overrides franchise display names.
    """
    week_objects: dict[int, Week] = {}
    for number, games in weeks.items():
        lineups: dict[str, Lineup] = {}
        matchups: list[tuple[str, str]] = []
        for home, away in games:
            home_score, away_score = home.score or 0.0, away.score or 0.0
            if home_score == away_score:
                home_result = away_result = "T"
            else:
                home_result, away_result = ("W", "L") if home_score > away_score else ("L", "W")
            lineups[home.franchise_id] = replace(home, result=home_result)
            lineups[away.franchise_id] = replace(away, result=away_result)
            matchups.append((home.franchise_id, away.franchise_id))
        week_objects[number] = Week(number=number, lineups=lineups, matchups=tuple(matchups))
    names = names or {}
    return Season(
        year=year,
        league_id="1",
        name="Test League",
        complete=complete,
        franchises={f: Franchise(f, names.get(f, f"Team {f}")) for f in franchises},
        starter_minimums=starter_minimums or {"QB": 1, "RB": 2, "WR": 2, "TE": 1},
        start_week=min(weeks) if weeks else 1,
        end_week=max(weeks) if weeks else 1,
        last_regular_season_week=last_regular_season_week,
        weeks=week_objects,
        bracket=bracket,
        standings=(),
        draft=(),
        round1_order=(),
        transactions=transactions or TransactionLog((), (), (), (), ()),
        players={pid: PlayerInfo(pid, name, position, "") for pid, (name, position) in players.items()},
    )
