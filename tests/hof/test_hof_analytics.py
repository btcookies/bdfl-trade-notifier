from synthetic import build_season, four_team_league

from hof.stats import analytics
from hof.stats.league import League

PLAYERS = {f"a{i}": (f"QB A{i}", "QB") for i in range(1, 5)}


def test_season_analytics_for_2020():
    league = four_team_league()
    season = analytics.season_analytics(league, league.season(2020))
    assert season.year == 2020
    assert [(w.week, w.playoff) for w in season.weeks] == [(1, False), (2, False), (3, True), (4, True)]
    assert [line.name for line in season.weeks[0].standings] == ["Alpha", "Gamma", "Beta", "Delta"]  # through week 1: Beta's 10.0 outscores Delta's 5.0
    assert [line.name for line in season.standings] == ["Gamma", "Alpha", "Delta", "Beta"]  # newest
    assert season.weeks[2].standings == season.weeks[1].standings  # playoff weeks keep the regular-season table
    assert season.weeks[0].power[0].name == "Alpha" and season.weeks[1].power[0].name == "Gamma"
    assert season.weeks[2].power == () and season.weeks[3].power == ()
    assert season.final_power == season.weeks[1].power and season.power_week == 2
    assert [a.key for a in season.weeks[3].awards][:2] == ["high_score", "low_score"]
    assert {fid: sum(c.values()) for fid, c in season.tally.items()} == {"0001": 15, "0002": 4, "0003": 9, "0004": 4}
    assert (season.awards_leaders, season.awards_leader_count) == (("0001",), 15)
    assert (season.luckiest.name, season.luckiest.luck) == ("Delta", 0.7)
    assert (season.unluckiest.name, season.unluckiest.luck) == ("Alpha", -0.7)


def test_in_progress_season_and_label_overrides():
    league = four_team_league()
    season = analytics.season_analytics(league, league.season(2021), {"high_score": "Big Number"})
    assert [w.week for w in season.weeks] == [1]
    assert season.weeks[0].awards[0].label == "Big Number"
    assert [line.name for line in season.final_power] == ["Alpha Prime", "Beta"]
    # both played franchises have luck 0.0; ties go to the name
    assert season.luckiest.name == "Alpha Prime" and season.unluckiest.name == "Alpha Prime"


def test_season_without_games():
    empty = build_season(2022, PLAYERS, {}, last_regular_season_week=2)
    season = analytics.season_analytics(League.build([empty]), empty)
    assert season.weeks == () and season.latest is None and season.standings == ()
    assert season.final_power == () and season.power_week is None
    assert (season.awards_leaders, season.awards_leader_count) == ((), 0)
    assert season.luckiest is None and season.unluckiest is None


def test_compute_covers_every_season():
    league = four_team_league()
    everything = analytics.compute(league)
    assert sorted(everything) == [2020, 2021]
    assert everything[2021].awards_leaders == ("0001",)
