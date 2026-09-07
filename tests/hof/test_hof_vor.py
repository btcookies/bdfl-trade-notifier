from synthetic import build_season, lineup

from hof.model.season import BracketGame
from hof.stats.vor import Start, baselines, starts

PLAYERS = {
    "q1": ("QB One", "QB"),
    "q2": ("QB Two", "QB"),
    "q3": ("QB Three", "QB"),
    "q4": ("QB Four", "QB"),
    "r1": ("RB One", "RB"),
    "r2": ("RB Two", "RB"),
    "r3": ("RB Three", "RB"),
    "r4": ("RB Four", "RB"),
    "x1": ("Mystery Man", "UNK"),
}


def week_one():
    return [
        (lineup("0001", {"q1": 30.0, "r1": 12.0}), lineup("0002", {"q2": 20.0, "r2": 9.0})),
        (lineup("0003", {"q3": 10.0, "r3": 6.0}), lineup("0004", {"q4": 5.0, "r4": 3.0})),
    ]


def test_baseline_is_the_median_score():
    season = build_season(2030, PLAYERS, {1: week_one()}, last_regular_season_week=1)
    base = baselines(season)
    # QB pool [30, 20, 10, 5], median rank (4+1)//2 = 2 -> the 2nd-best score, 20.0.
    assert base[(1, "QB")] == 20.0
    # RB pool [12, 9, 6, 3], median rank (4+1)//2 = 2 -> the 2nd-best score, 9.0.
    assert base[(1, "RB")] == 9.0


def test_start_values_subtract_the_baseline():
    season = build_season(2030, PLAYERS, {1: week_one()}, last_regular_season_week=1)
    rows = starts(season)
    assert len(rows) == 8
    by_player = {s.player_id: s for s in rows}
    # QB baseline 20.0 (see above): q1 scored 30.0, so vor = 30.0 - 20.0 = 10.0.
    assert by_player["q1"] == Start(2030, 1, "0001", "q1", "QB", 30.0, 10.0, False)
    # q4 scored 5.0 against the same 20.0 baseline: vor = 5.0 - 20.0 = -15.0.
    assert by_player["q4"].vor == -15.0
    # RB baseline 9.0: r1 scored 12.0, so vor = 12.0 - 9.0 = 3.0.
    assert by_player["r1"].vor == 3.0
    # r4 scored 3.0 against the same 9.0 baseline: vor = 3.0 - 9.0 = -6.0.
    assert by_player["r4"].vor == -6.0


def test_non_counted_lineups_feed_the_pool_but_yield_no_starts():
    weeks = {
        1: week_one(),
        2: [
            (lineup("0001", {"q1": 12.0}), lineup("0002", {"q2": 30.0})),  # bracket game
            (lineup("0003", {"q3": 8.0}), lineup("0004", {"q4": 2.0})),  # consolation, not counted
        ],
    }
    bracket = (BracketGame(2, "1", 0, "0001", "0002", 1, 2),)
    season = build_season(2030, PLAYERS, weeks, last_regular_season_week=1, bracket=bracket)
    base = baselines(season)
    # QB pool [30, 12, 8, 2] (all four week-2 lineups feed the pool, including the consolation
    # game), median rank (4+1)//2 = 2 -> the 2nd-best score, 12.0. q4's consolation start still
    # sets the baseline even though it produces no start of its own.
    assert base[(2, "QB")] == 12.0
    week_two = [s for s in starts(season) if s.week == 2]
    assert {s.player_id for s in week_two} == {"q1", "q2"}
    assert all(s.playoff for s in week_two)
    # q2 scored 30.0 against the 12.0 baseline: vor = 30.0 - 12.0 = 18.0.
    assert next(s for s in week_two if s.player_id == "q2").vor == 18.0


def test_missing_score_counts_as_zero_points_but_does_not_set_the_baseline():
    weeks = {1: [(lineup("0001", {"q1": None}), lineup("0002", {"q2": 10.0}))]}
    season = build_season(2030, PLAYERS, weeks, last_regular_season_week=1, franchises=("0001", "0002"))
    rows = {s.player_id: s for s in starts(season)}
    assert rows["q1"].points == 0.0
    # q1 never fed the baseline pool (MFL never scored them), leaving a pool of one: q2's 10.0.
    # A pool of one is its own baseline, median rank (1+1)//2 = 1 -> 10.0. q2 sits at replacement,
    # vor = 10.0 - 10.0 = 0.0; q1 scores 0.0 against the same baseline, vor = 0.0 - 10.0 = -10.0.
    assert rows["q2"].vor == 0.0
    assert rows["q1"].vor == -10.0


def test_an_unscored_starter_does_not_drag_the_baseline_to_a_phantom_zero():
    """A franchise that set no real lineup (eliminated, inactive) still has a starter slot MFL
    lists with no score. Pooling that as a real 0.0 would still bias the median toward zero
    whenever such lineups make up a large share of a position's pool. It must not count toward
    the pool at all."""
    weeks = {
        1: [
            (lineup("0001", {"q1": 20.0}), lineup("0002", {"q2": 8.0})),
            (lineup("0003", {"q3": 12.0}), lineup("0004", {"q4": None})),
        ]
    }
    season = build_season(2030, PLAYERS, weeks, last_regular_season_week=1)
    base = baselines(season)
    # q4 has no recorded score and is excluded, leaving a QB pool of [20, 12, 8] (three
    # scorers). Median rank (3+1)//2 = 2 -> the 2nd-best score, 12.0.
    assert base[(1, "QB")] == 12.0


def test_unknown_position_is_excluded_from_pools_and_worth_zero():
    weeks = {1: [(lineup("0001", {"q1": 20.0, "x1": 50.0}), lineup("0002", {"q2": 10.0}))]}
    season = build_season(2030, PLAYERS, weeks, last_regular_season_week=1, franchises=("0001", "0002"))
    base = baselines(season)
    assert set(base) == {(1, "QB")}
    # QB pool [20, 10], median rank (2+1)//2 = 1 -> the best score, 20.0.
    assert base[(1, "QB")] == 20.0
    mystery = next(s for s in starts(season) if s.player_id == "x1")
    assert (mystery.points, mystery.vor) == (50.0, 0.0)


def test_odd_pool_uses_the_middle_score():
    players = {**PLAYERS, "q5": ("QB Five", "QB"), "q6": ("QB Six", "QB")}
    weeks = {
        1: [
            (lineup("0001", {"q1": 50.0}), lineup("0002", {"q2": 40.0})),
            (lineup("0003", {"q3": 30.0}), lineup("0004", {"q4": 20.0})),
            (lineup("0005", {"q5": 10.0}), lineup("0006", {"q6": None})),
        ]
    }
    season = build_season(
        2030, players, weeks, last_regular_season_week=1, franchises=("0001", "0002", "0003", "0004", "0005", "0006")
    )
    base = baselines(season)
    # q6 has no recorded score and doesn't feed the pool, leaving five real QB scores:
    # [50, 40, 30, 20, 10]. Median rank (5+1)//2 = 3 -> the 3rd-best score, 30.0.
    assert base[(1, "QB")] == 30.0


def test_pool_of_one_is_its_own_baseline():
    weeks = {1: [(lineup("0001", {"q1": 17.0}), lineup("0002", {"r2": 8.0}))]}
    season = build_season(2030, PLAYERS, weeks, last_regular_season_week=1, franchises=("0001", "0002"))
    base = baselines(season)
    # Exactly one QB starter and one RB starter this week; a pool of one is its own baseline,
    # median rank (1+1)//2 = 1.
    assert base[(1, "QB")] == 17.0
    assert base[(1, "RB")] == 8.0
    rows = {s.player_id: s for s in starts(season)}
    # Each player scores exactly their own baseline: vor = 0.0.
    assert rows["q1"].vor == 0.0
    assert rows["r2"].vor == 0.0
