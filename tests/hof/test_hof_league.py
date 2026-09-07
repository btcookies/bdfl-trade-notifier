from synthetic import build_season, lineup

from hof.model.players import PlayerInfo
from hof.stats.league import Era, League

PLAYERS = {"q1": ("QB One", "QB"), "q2": ("QB Two", "QB"), "r1": ("RB One", "RB")}


def two_seasons():
    s1 = build_season(
        2020,
        PLAYERS,
        {1: [(lineup("0001", {"q1": 20.0}, bench={"r1": 4.0}), lineup("0002", {"q2": 10.0}))]},
        last_regular_season_week=1,
        franchises=("0001", "0002"),
        names={"0001": "Old Name", "0002": "Team Two"},
    )
    s2 = build_season(
        2021,
        PLAYERS,
        {1: [(lineup("0001", {"q1": 15.0}), lineup("0002", {"q2": 25.0}, bench={"r1": 1.0}))]},
        last_regular_season_week=1,
        franchises=("0001", "0002"),
        names={"0001": "New  Name", "0002": "team two"},
    )
    return League.build([s1, s2])


def test_build_computes_starts_per_season():
    league = two_seasons()
    assert [s.year for s in league.seasons] == [2020, 2021]
    assert {year: len(rows) for year, rows in league.starts.items()} == {2020: 2, 2021: 2}
    assert len(league.all_starts()) == 4
    assert league.latest.year == 2021
    assert league.season(2020).year == 2020


def test_current_name_and_eras_ignore_cosmetic_renames():
    league = two_seasons()
    assert league.franchise_ids() == ["0001", "0002"]
    assert league.current_name("0001") == "New  Name"
    assert league.name_in("0001", 2020) == "Old Name"
    assert league.eras("0001") == [Era("0001", "Old Name", 2020, 2020), Era("0001", "New  Name", 2021, 2021)]
    # "Team Two" and "team two" differ only by case, so they are one era named by the newest spelling
    assert league.eras("0002") == [Era("0002", "team two", 2020, 2021)]
    assert league.era_of("0002", 2020).name == "team two"


def test_player_info_prefers_the_newest_season():
    s1 = build_season(2020, {"p": ("Old Spelling", "WR")}, {1: [(lineup("0001", {"p": 1.0}), lineup("0002", {}))]}, 1, franchises=("0001", "0002"))
    s2 = build_season(2021, {"p": ("New Spelling", "WR")}, {}, 1, franchises=("0001", "0002"))
    league = League.build([s1, s2])
    assert league.player_info("p").name == "New Spelling"
    assert league.player_info("zzz") == PlayerInfo.unknown("zzz")


def test_rosters_track_starters_and_bench_by_week():
    league = two_seasons()
    rosters = league.rosters(2020)
    assert rosters == {1: {"q1": {"0001"}, "r1": {"0001"}, "q2": {"0002"}}}
    assert league.latest_rostered_week() == (2021, 1)


def test_completed_and_name_lookup():
    league = two_seasons()
    assert [s.year for s in league.completed()] == [2020, 2021]
    assert league.franchise_by_name() == {"old name": "0001", "new name": "0001", "team two": "0002"}
