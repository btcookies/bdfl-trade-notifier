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


def test_baseline_is_the_nth_best_starter_or_the_lowest_when_short():
    season = build_season(2030, PLAYERS, {1: week_one()}, last_regular_season_week=1)
    base = baselines(season)
    # Four franchises with one required QB: the 4th-best QB (5.0) is replacement level.
    assert base[(1, "QB")] == 5.0
    # Two required RBs would want the 8th-best, but only four started: the lowest (3.0) is used.
    assert base[(1, "RB")] == 3.0


def test_start_values_subtract_the_baseline():
    season = build_season(2030, PLAYERS, {1: week_one()}, last_regular_season_week=1)
    rows = starts(season)
    assert len(rows) == 8
    by_player = {s.player_id: s for s in rows}
    assert by_player["q1"] == Start(2030, 1, "0001", "q1", "QB", 30.0, 25.0, False)
    assert by_player["q4"].vor == 0.0
    assert by_player["r1"].vor == 9.0
    assert by_player["r4"].vor == 0.0


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
    assert base[(2, "QB")] == 2.0  # q4's consolation start still sets the baseline
    week_two = [s for s in starts(season) if s.week == 2]
    assert {s.player_id for s in week_two} == {"q1", "q2"}
    assert all(s.playoff for s in week_two)
    assert next(s for s in week_two if s.player_id == "q2").vor == 28.0


def test_missing_score_counts_as_zero_points_but_does_not_set_the_baseline():
    weeks = {1: [(lineup("0001", {"q1": None}), lineup("0002", {"q2": 10.0}))]}
    season = build_season(2030, PLAYERS, weeks, last_regular_season_week=1, franchises=("0001", "0002"))
    rows = {s.player_id: s for s in starts(season)}
    assert rows["q1"].points == 0.0
    # q1 never fed the baseline pool (MFL never scored them), so q2's 10.0 -- the only real QB
    # performance -- is the (lowest-available) baseline: q2 sits at replacement, q1 below it.
    assert rows["q2"].vor == 0.0
    assert rows["q1"].vor == -10.0


def test_an_unscored_starter_does_not_drag_the_baseline_to_a_phantom_zero():
    """A franchise that set no real lineup (eliminated, inactive) still has a starter slot MFL
    lists with no score. Pooling that as a real 0.0 would collapse replacement level whenever a
    position's required count exactly equals the number of played lineups -- which happens every
    week for a fixed one-starter position like QB. It must not count toward the pool at all."""
    weeks = {
        1: [
            (lineup("0001", {"q1": 20.0}), lineup("0002", {"q2": 8.0})),
            (lineup("0003", {"q3": 12.0}), lineup("0004", {"q4": None})),
        ]
    }
    season = build_season(2030, PLAYERS, weeks, last_regular_season_week=1)
    base = baselines(season)
    assert base[(1, "QB")] == 8.0


def test_unknown_position_is_excluded_from_pools_and_worth_zero():
    weeks = {1: [(lineup("0001", {"q1": 20.0, "x1": 50.0}), lineup("0002", {"q2": 10.0}))]}
    season = build_season(2030, PLAYERS, weeks, last_regular_season_week=1, franchises=("0001", "0002"))
    base = baselines(season)
    assert set(base) == {(1, "QB")}
    mystery = next(s for s in starts(season) if s.player_id == "x1")
    assert (mystery.points, mystery.vor) == (50.0, 0.0)
