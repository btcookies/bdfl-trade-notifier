from dataclasses import replace

from synthetic import build_season, four_team_league, lineup

from hof.stats import awards
from hof.stats.awards import AWARD_KEYS, DEFAULT_LABELS, Award
from hof.stats.league import League

PLAYERS = {f"a{i}": (f"QB A{i}", "QB") for i in range(1, 5)}


def by_key(items):
    return {award.key: award for award in items}


def test_award_keys_and_default_labels_line_up():
    assert AWARD_KEYS == ("high_score", "low_score", "blowout", "closest", "best_lineup", "worst_lineup", "lucky_win", "unlucky_loss", "best_benched")
    assert tuple(DEFAULT_LABELS) == AWARD_KEYS
    assert awards.labels_with(None) == DEFAULT_LABELS
    assert awards.labels_with({"low_score": "Golden Goose Egg"})["low_score"] == "Golden Goose Egg"
    assert awards.labels_with({"low_score": "Golden Goose Egg"})["high_score"] == "Highest score"


def test_week_one_awards():
    league = four_team_league()
    week = awards.week_awards(league, league.season(2020), 1)
    assert [a.key for a in week] == list(AWARD_KEYS[:-1])  # no bench players, so no best_benched
    got = by_key(week)
    assert got["high_score"] == Award("high_score", "Highest score", "0001", "Alpha", "0001", 20.0, "pts", "beat Beta 20.0–10.0")
    assert got["low_score"] == Award("low_score", "Lowest score", "0004", "Delta", "0004", 5.0, "pts", "lost to Gamma 5.0–15.0")
    assert got["blowout"] == Award("blowout", "Biggest blowout", "0001", "Alpha", "0001", 10.0, "pts", "over Beta, 20.0–10.0")
    assert got["closest"] == Award("closest", "Closest game", "0001", "Alpha", "0001", 10.0, "pts", "over Beta, 20.0–10.0")
    assert got["best_lineup"] == Award("best_lineup", "Best lineup", "0001", "Alpha", "0001", 1.0, "pct", "20.0 of 20.0 possible")
    assert got["worst_lineup"] == Award("worst_lineup", "Most points left on the bench", "0002", "Beta", "0002", 4.0, "pts", "10.0 of 14.0 possible")
    assert got["lucky_win"] == Award("lucky_win", "Luckiest win", "0003", "Gamma", "0003", 15.0, "pts", "would have gone 2-1-0 against the field")
    assert got["unlucky_loss"] == Award("unlucky_loss", "Unluckiest loss", "0002", "Beta", "0002", 10.0, "pts", "would have gone 1-2-0 against the field")


def test_week_two_awards_and_label_overrides():
    league = four_team_league()
    got = by_key(awards.week_awards(league, league.season(2020), 2, {"lucky_win": "Horseshoe"}))
    assert (got["high_score"].holder_name, got["high_score"].value) == ("Gamma", 18.0)
    assert (got["low_score"].holder_name, got["low_score"].value) == ("Beta", 9.0)
    assert (got["blowout"].holder_name, got["blowout"].value, got["blowout"].detail) == ("Gamma", 6.0, "over Alpha, 18.0–12.0")
    assert (got["closest"].holder_name, got["closest"].value) == ("Delta", 2.0)
    assert (got["best_lineup"].holder_name, got["worst_lineup"].holder_name, got["worst_lineup"].value) == ("Gamma", "Gamma", 0.0)
    assert (got["lucky_win"].label, got["lucky_win"].holder_name, got["lucky_win"].detail) == ("Horseshoe", "Delta", "would have gone 1-2-0 against the field")
    assert (got["unlucky_loss"].holder_name, got["unlucky_loss"].value) == ("Alpha", 12.0)


def test_playoff_week_awards_cover_bracket_games_without_all_play_detail():
    league = four_team_league()
    got = by_key(awards.week_awards(league, league.season(2020), 4))
    assert (got["high_score"].holder_name, got["low_score"].holder_name) == ("Alpha", "Gamma")
    assert got["lucky_win"] == Award("lucky_win", "Luckiest win", "0001", "Alpha", "0001", 30.0, "pts", "")
    assert got["unlucky_loss"] == Award("unlucky_loss", "Unluckiest loss", "0003", "Gamma", "0003", 20.0, "pts", "")
    assert awards.week_awards(league, league.season(2020), 9) == []


def test_tie_is_the_closest_game_and_gives_no_lucky_or_unlucky():
    season = build_season(
        2020, PLAYERS,
        {1: [(lineup("0001", {"a1": 10.0}), lineup("0002", {"a2": 10.0}))]},
        last_regular_season_week=1, franchises=("0001", "0002"),
    )
    got = by_key(awards.week_awards(League.build([season]), season, 1))
    assert got["closest"] == Award("closest", "Closest game", "0001", "Team 0001", "0001", 0.0, "pts", "tied with Team 0002, 10.0–10.0")
    assert got["blowout"].value == 0.0
    assert got["high_score"].detail == "tied Team 0002 10.0–10.0"
    assert "lucky_win" not in got and "unlucky_loss" not in got


def test_best_benched_player_and_lineup_efficiency():
    players = {**PLAYERS, "b1": ("RB B1", "RB"), "b2": ("RB B2", "RB")}
    season = build_season(
        2020, players,
        {1: [
            (lineup("0001", {"a1": 20.0}, bench={"b1": 25.0}, opt_pts=45.0), lineup("0002", {"a2": 10.0}, bench={"b2": 12.0}, opt_pts=22.0)),
        ]},
        last_regular_season_week=1, franchises=("0001", "0002"),
    )
    got = by_key(awards.week_awards(League.build([season]), season, 1))
    assert got["best_benched"] == Award("best_benched", "Best player on a bench", "b1", "RB B1", "0001", 25.0, "pts", "on Team 0001's bench")
    assert got["best_lineup"] == Award("best_lineup", "Best lineup", "0002", "Team 0002", "0002", 0.455, "pct", "10.0 of 22.0 possible")
    assert got["worst_lineup"] == Award("worst_lineup", "Most points left on the bench", "0001", "Team 0001", "0001", 25.0, "pts", "20.0 of 45.0 possible")


def test_no_lineup_awards_without_optimal_points():
    season = build_season(
        2020, PLAYERS,
        {1: [(lineup("0001", {"a1": 20.0}), lineup("0002", {"a2": 10.0}))]},
        last_regular_season_week=1, franchises=("0001", "0002"),
    )
    week = season.weeks[1]
    lineups = {fid: replace(lu, opt_pts=None) for fid, lu in week.lineups.items()}
    season = replace(season, weeks={1: replace(week, lineups=lineups)})
    keys = [a.key for a in awards.week_awards(League.build([season]), season, 1)]
    assert "best_lineup" not in keys and "worst_lineup" not in keys and "high_score" in keys


def test_format_value():
    assert awards.format_value(20.0, "pts") == "20.0"
    assert awards.format_value(0.4545, "pct") == "45.5%"
    assert awards.format_value(0.7, "wins") == "+0.7"
    assert awards.format_value(-0.7, "wins") == "-0.7"


def test_tally_and_leaders_for_the_season():
    league = four_team_league()
    season = league.season(2020)
    weeks = [awards.week_awards(league, season, week) for week in (1, 2, 3, 4)]
    counts = awards.tally(weeks, season.franchises)
    assert {fid: sum(c.values()) for fid, c in counts.items()} == {"0001": 15, "0002": 4, "0003": 9, "0004": 4}
    assert counts["0001"]["high_score"] == 3 and counts["0002"]["worst_lineup"] == 1
    assert set(counts["0004"]) == set(AWARD_KEYS)
    assert awards.leaders(counts) == (("0001",), 15)
    assert awards.leaders({"0001": dict.fromkeys(AWARD_KEYS, 0)}) == ((), 0)
    tied = {"0001": {**dict.fromkeys(AWARD_KEYS, 0), "high_score": 2}, "0002": {**dict.fromkeys(AWARD_KEYS, 0), "low_score": 2}}
    assert awards.leaders(tied) == (("0001", "0002"), 2)
