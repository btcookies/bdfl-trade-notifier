from synthetic import build_season, four_team_league, lineup

from hof.stats import power
from hof.stats.league import League

PLAYERS = {f"a{i}": (f"QB A{i}", "QB") for i in range(1, 5)}


def test_first_ranked_week_has_no_previous_rank():
    league = four_team_league()
    lines = power.rankings(league, league.season(2020), through_week=1)
    assert [(line.rank, line.name, line.score, line.previous_rank, line.movement) for line in lines] == [
        (1, "Alpha", 1.0, None, None),
        (2, "Gamma", 0.767, None, None),
        (3, "Beta", 0.233, None, None),
        (4, "Delta", 0.0, None, None),
    ]
    gamma = lines[1]
    assert (gamma.allplay_pct, gamma.win_pct, gamma.form) == (0.667, 1.0, 0.667)


def test_second_week_ranks_and_movement():
    league = four_team_league()
    lines = power.rankings(league, league.season(2020), through_week=2)
    assert [(line.rank, line.name, line.score, line.previous_rank, line.movement) for line in lines] == [
        (1, "Gamma", 0.883, 2, 1),
        (2, "Alpha", 0.733, 1, -1),
        (3, "Delta", 0.267, 4, 1),
        (4, "Beta", 0.117, 3, -1),
    ]


def test_playoff_weeks_keep_the_final_regular_season_ranking():
    league = four_team_league()
    season = league.season(2020)
    assert power.rankings(league, season, through_week=4) == power.rankings(league, season, through_week=2)
    assert power.rankings(league, season, through_week=None) == power.rankings(league, season, through_week=2)
    assert power.ranked_weeks(season) == [1, 2]


def test_form_pools_the_last_three_weeks():
    weeks = {
        1: [(lineup("0001", {"a1": 20.0}), lineup("0002", {"a2": 10.0}))],
        2: [(lineup("0001", {"a1": 20.0}), lineup("0002", {"a2": 10.0}))],
        3: [(lineup("0001", {"a1": 20.0}), lineup("0002", {"a2": 10.0}))],
        4: [(lineup("0001", {"a1": 10.0}), lineup("0002", {"a2": 20.0}))],
    }
    season = build_season(2020, PLAYERS, weeks, last_regular_season_week=4, franchises=("0001", "0002"))
    lines = power.rankings(League.build([season]), season, through_week=4)
    top = lines[0]
    assert top.franchise_id == "0001"
    assert (top.allplay_pct, top.win_pct, top.form) == (0.75, 0.75, 0.667)  # form: weeks 2-4, 2-1
    assert top.score == 0.733  # 0.375 + 0.225 + 0.133
    assert (lines[1].form, lines[1].score) == (0.333, 0.267)


def test_ties_break_on_points_for_then_name():
    weeks = {1: [(lineup("0001", {"a1": 20.0}), lineup("0002", {"a2": 20.0})), (lineup("0003", {"a3": 30.0}), lineup("0004", {"a4": 30.0}))]}
    season = build_season(2020, PLAYERS, weeks, last_regular_season_week=2)
    lines = power.rankings(League.build([season]), season, through_week=1)
    # Both games are ties, so every win % is .5. 0003 and 0004 scored 30 against two 20s, so
    # their all-play is 2-0-1 (.833) and 0001/0002 are 0-2-1 (.167). Score for 0003 and 0004:
    # 0.5 × .833 + 0.3 × .5 + 0.2 × .833 = 0.733; equal scores and equal points for (30.0), so
    # the name decides.
    assert [(line.name, line.score) for line in lines] == [("Team 0003", 0.733), ("Team 0004", 0.733), ("Team 0001", 0.267), ("Team 0002", 0.267)]
    assert [line.rank for line in lines] == [1, 2, 3, 4]


def test_franchises_without_a_game_are_not_ranked():
    league = four_team_league()
    lines = power.rankings(league, league.season(2021), through_week=1)
    assert [(line.rank, line.name, line.score) for line in lines] == [(1, "Alpha Prime", 1.0), (2, "Beta", 0.0)]


def test_no_ranking_before_the_first_game():
    season = build_season(2020, PLAYERS, {}, last_regular_season_week=2)
    assert power.rankings(League.build([season]), season, through_week=None) == []
