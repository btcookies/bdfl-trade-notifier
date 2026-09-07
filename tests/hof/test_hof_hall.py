from synthetic import four_team_league

from hof.config import HallRules
from hof.stats import careers, franchises, hall
from hof.stats.hall import FranchisePlaque, PlayerPlaque, WatchEntry


def build(rules):
    league = four_team_league()
    return hall.hall_of_fame(league, careers.careers(league), franchises.all_franchises(league), rules)


def test_players_and_franchises_are_inducted_in_the_season_they_cross_the_line():
    # 2020 (finished) vor totals: a1 36.0, a3 22.0, a2 -2.0, a4 -10.0 (see test_hof_franchises
    # and test_hof_records for the week-by-week arithmetic). Only a1 clears 36 with >=3 starts.
    result = build(HallRules(player_min_vor=36, player_min_starts=3, franchise_min_titles=1, watch_list_margin=50))
    assert result.players == (
        PlayerPlaque("a1", "QB A1", "QB", 2020, ("Alpha Prime",), 5, 97.0, 41.0, 1),
    )
    assert result.franchises == (FranchisePlaque("0001", "Alpha Prime", 2020, 1, "2-1-0", 0.667),)
    # a2's full career vor (2020's -2.0 plus 2021 Week 1's 0.0) is -2.0; needed = 36 - (-2) = 38.0.
    assert result.watch_list == (WatchEntry("a2", "QB A2", "QB", 4, -2.0, 38.0, 0),)
    assert result.rules.player_min_vor == 36


def test_unfinished_seasons_do_not_induct_but_feed_the_watch_list():
    # a1's only finished season (2020) reaches 36.0 vor -- short of the 45 threshold. The
    # in-progress 2021 Week 1 adds 5.0 more (a1 is not the baseline in that two-QB pool under the
    # two-thirds rule -- the worse score, a2's 5.0, is -- so a1 scores 10.0 - 5.0 = 5.0 that
    # week), bringing the full career total to 41.0: still short of induction (which only counts
    # finished seasons), but well within the watch-list margin.
    result = build(HallRules(player_min_vor=45, player_min_starts=3, franchise_min_titles=2, watch_list_margin=10))
    assert result.players == ()
    assert result.franchises == ()
    assert result.watch_list == (WatchEntry("a1", "QB A1", "QB", 5, 41.0, 4.0, 0),)


def test_class_years_follow_cumulative_totals():
    league = four_team_league()
    # Only a1 (36.0) clears 30 among the 2020 finished-season totals (a3 22.0, a2 -2.0, a4 -10.0).
    assert hall.player_class_years(league, HallRules(player_min_vor=30, player_min_starts=3)) == {"a1": 2020}
    # -5 sits strictly between a4's -10.0 (excluded) and a2's -2.0 (included), so a1, a2, and a3
    # all clear it in 2020.
    assert hall.player_class_years(league, HallRules(player_min_vor=-5, player_min_starts=1)) == {"a1": 2020, "a3": 2020, "a2": 2020}
    assert hall.franchise_class_years(league, HallRules(franchise_min_titles=1)) == {"0001": 2020}


def test_inactive_players_are_not_on_the_watch_list():
    result = build(HallRules(player_min_vor=10, player_min_starts=3, franchise_min_titles=1, watch_list_margin=500))
    assert [w.player_id for w in result.watch_list] == ["a2"]  # a3 and a4 were not rostered in the newest week
