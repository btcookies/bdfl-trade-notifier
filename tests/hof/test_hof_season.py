import json

import pytest

from hof.model.players import PlayerInfo
from hof.model.season import (
    BracketGame,
    Franchise,
    Game,
    Lineup,
    Season,
    Standing,
    Week,
    normalize_name,
    parse_bracket,
    parse_draft,
    parse_league,
    parse_standings,
    parse_week,
)
from hof.model.transactions import TransactionLog


def load(fixtures_dir, name):
    return json.loads((fixtures_dir / "raw" / "2020" / name).read_text())


def test_parse_league(fixtures_dir):
    settings = parse_league(load(fixtures_dir, "league.json"))
    assert settings.name == "Barbara Dodson's Fantasy League"
    assert len(settings.franchises) == 12
    assert settings.franchises["0001"] == Franchise("0001", "The Youth Academy", "02")
    assert settings.starter_minimums == {"QB": 1, "RB": 2, "WR": 2, "TE": 1}
    assert (settings.start_week, settings.end_week, settings.last_regular_season_week) == (1, 17, 13)


def test_parse_regular_season_week(fixtures_dir):
    week = parse_week(load(fixtures_dir, "weeklyResults/W01.json"), number=1)
    assert week.number == 1
    assert len(week.matchups) == 6
    assert len(week.lineups) == 12
    assert week.matchups[0] == ("0012", "0009")  # isHome=1 is listed second in the raw body
    lineup = week.lineups["0009"]
    assert lineup.score == 104.8
    assert lineup.result == "W"
    assert lineup.opt_pts == 117.7
    assert len(lineup.starters) == 8
    assert lineup.starters[0] == "9099"
    assert lineup.points("9099") == 24.9
    assert lineup.points("no-such-player") == 0.0
    assert lineup.played


def test_parse_playoff_week_keeps_every_lineup(fixtures_dir):
    week = parse_week(load(fixtures_dir, "weeklyResults/W15.json"), number=15)
    assert len(week.matchups) == 2
    assert len(week.lineups) == 12
    assert all(lineup.played for lineup in week.lineups.values())


def test_parse_unplayed_week():
    body = {
        "weeklyResults": {
            "week": "5",
            "matchup": [
                {"franchise": [{"id": "0012", "result": "T", "isHome": "0"}, {"id": "0005", "result": "T", "isHome": "1"}]}
            ],
        }
    }
    week = parse_week(body, number=5)
    assert week.matchups == (("0005", "0012"),)
    assert not week.lineups["0012"].played
    assert week.lineups["0012"].score is None


def test_parse_bracket(fixtures_dir):
    games = parse_bracket(load(fixtures_dir, "playoffBracket-1.json"))
    assert len(games) == 5
    assert games[0] == BracketGame(week=14, game_id="1", round_index=0, home_id="0001", away_id="0003", home_seed=3, away_seed=6)
    assert games[-1].week == 16
    assert games[-1].round_index == 2
    assert (games[-1].home_id, games[-1].away_id) == ("0010", "0002")


def test_parse_bracket_before_it_is_set():
    body = {"playoffBracket": {"playoffRound": [{"week": "15", "playoffGame": [{"game_id": "1", "home": {"seed": "3"}, "away": {"seed": "6"}}]}]}}
    games = parse_bracket(body)
    assert games == (BracketGame(15, "1", 0, None, None, 3, 6),)


def test_parse_standings(fixtures_dir):
    standings = parse_standings(load(fixtures_dir, "standings.json"))
    assert len(standings) == 12
    assert standings[0] == Standing("0002", 10, 3, 0, 1896.6, 1157.4, "3-1-0", "W3")
    assert standings[-1].franchise_id == "0004"


def test_parse_draft(fixtures_dir):
    picks, order = parse_draft(load(fixtures_dir, "draftResults.json"))
    assert len(picks) == 48
    assert (picks[0].round, picks[0].pick, picks[0].franchise_id, picks[0].player_id) == (1, 1, "0006", "14803")
    assert order[:3] == ("0006", "0012", "0004")


def test_normalize_name():
    assert normalize_name("  Free   Hernandez ") == "free hernandez"


# --- Season behaviour on a small synthetic season ------------------------------------------


def lineup(franchise_id, starters, result=None):
    scores = dict(starters)
    return Lineup(
        franchise_id=franchise_id,
        starters=tuple(starters),
        nonstarters=(),
        scores=scores,
        score=round(sum(scores.values()), 1),
        opt_pts=round(sum(scores.values()), 1),
        result=result,
    )


def synthetic_season():
    week1 = Week(
        number=1,
        lineups={
            "0001": lineup("0001", {"q1": 20.0}, "W"),
            "0002": lineup("0002", {"q2": 10.0}, "L"),
            "0003": lineup("0003", {"q3": 15.0}, "W"),
            "0004": lineup("0004", {"q4": 5.0}, "L"),
        },
        matchups=(("0001", "0002"), ("0003", "0004")),
    )
    week2 = Week(  # playoff week: one bracket game, one consolation matchup
        number=2,
        lineups={
            "0001": lineup("0001", {"q1": 12.0}, "L"),
            "0003": lineup("0003", {"q3": 12.5}, "W"),
            "0002": lineup("0002", {"q2": 30.0}, "W"),
            "0004": lineup("0004", {"q4": 1.0}, "L"),
        },
        matchups=(("0001", "0003"), ("0002", "0004")),
    )
    week3 = Week(number=3, lineups={}, matchups=(("0001", "0003"),))  # unplayed
    return Season(
        year=2030,
        league_id="1",
        name="Test",
        complete=False,
        franchises={f: Franchise(f, f"Team {f}") for f in ("0001", "0002", "0003", "0004")},
        starter_minimums={"QB": 1},
        start_week=1,
        end_week=3,
        last_regular_season_week=1,
        weeks={1: week1, 2: week2, 3: week3},
        bracket=(BracketGame(2, "1", 0, "0003", "0001", 1, 2),),
        standings=(),
        draft=(),
        round1_order=(),
        transactions=TransactionLog((), (), (), (), ()),
        players={p: PlayerInfo(p, p.upper(), "QB", "") for p in ("q1", "q2", "q3", "q4")},
    )


def test_games_counts_regular_matchups_and_bracket_games_only():
    season = synthetic_season()
    games = season.games()
    assert [(g.week, g.playoff, g.round_name) for g in games] == [
        (1, False, None),
        (1, False, None),
        (2, True, "Final"),
    ]
    final = games[-1]
    assert final.winner.franchise_id == "0003"
    assert final.loser.franchise_id == "0001"
    assert final.margin == 0.5
    assert final.opponent_of("0001").franchise_id == "0003"
    assert final.lineup_of("0003").score == 12.5
    assert season.champion_id == "0003"
    assert season.final == final


def test_ties_have_no_winner():
    game = Game(2030, 1, lineup("0001", {"a": 1.0}), lineup("0002", {"b": 1.0}), playoff=False)
    assert game.winner is None and game.loser is None and game.tie


def test_round_names_count_back_from_the_final():
    season = synthetic_season()
    three = Season(**{**season.__dict__, "bracket": (BracketGame(2, "1", 0, None, None, 3, 6), BracketGame(3, "2", 1, None, None, 1, None), BracketGame(4, "3", 2, None, None, None, None))})
    assert [three.round_name(i) for i in range(3)] == ["Quarterfinal", "Semifinal", "Final"]
    assert three.playoff_weeks() == {2, 3, 4}


def test_franchise_name_and_player_fallbacks():
    season = synthetic_season()
    assert season.franchise_name("0001") == "Team 0001"
    assert season.franchise_name("0099") == "Franchise 0099"
    assert season.player("zzz").name == "Unknown player (#zzz)"


@pytest.mark.parametrize("value, expected", [("104.8", 104.8), ("", None), (None, None), ("x", None)])
def test_float_or_none(value, expected):
    from hof.model.season import float_or_none

    assert float_or_none(value) == expected
