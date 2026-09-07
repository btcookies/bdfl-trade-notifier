from synthetic import four_team_league

from hof.config import HallRules
from hof.stats import careers, franchises, hall
from hof.stats.hall import FranchisePlaque, PlayerPlaque, WatchEntry


def build(rules):
    league = four_team_league()
    return hall.hall_of_fame(league, careers.careers(league), franchises.all_franchises(league), rules)


def test_players_and_franchises_are_inducted_in_the_season_they_cross_the_line():
    result = build(HallRules(player_min_vor=40, player_min_starts=3, franchise_min_titles=1, watch_list_margin=50))
    assert result.players == (
        PlayerPlaque("a1", "QB A1", "QB", 2020, ("Alpha Prime",), 5, 97.0, 53.0, 1),
    )
    assert result.franchises == (FranchisePlaque("0001", "Alpha Prime", 2020, 1, "2-1-0", 0.667),)
    assert result.watch_list == (WatchEntry("a2", "QB A2", "QB", 4, 10.0, 30.0, 0),)
    assert result.rules.player_min_vor == 40


def test_unfinished_seasons_do_not_induct_but_feed_the_watch_list():
    # a1 has 48 value after 2020 and 53 after the in-progress 2021: over 50 only once 2021 counts
    result = build(HallRules(player_min_vor=50, player_min_starts=3, franchise_min_titles=2, watch_list_margin=10))
    assert result.players == ()
    assert result.franchises == ()
    assert result.watch_list == (WatchEntry("a1", "QB A1", "QB", 5, 53.0, 0.0, 0),)


def test_class_years_follow_cumulative_totals():
    league = four_team_league()
    assert hall.player_class_years(league, HallRules(player_min_vor=40, player_min_starts=3)) == {"a1": 2020}
    assert hall.player_class_years(league, HallRules(player_min_vor=10, player_min_starts=1)) == {"a1": 2020, "a3": 2020, "a2": 2020}
    assert hall.franchise_class_years(league, HallRules(franchise_min_titles=1)) == {"0001": 2020}


def test_inactive_players_are_not_on_the_watch_list():
    result = build(HallRules(player_min_vor=40, player_min_starts=3, franchise_min_titles=1, watch_list_margin=500))
    assert [w.player_id for w in result.watch_list] == ["a2"]  # a3 and a4 were not rostered in the newest week
