from synthetic import build_season, four_team_league, lineup

from hof.stats import allplay
from hof.stats.league import League

PLAYERS = {f"a{i}": (f"QB A{i}", "QB") for i in range(1, 5)}


def test_all_play_week_compares_every_counted_score():
    season = four_team_league().season(2020)
    rows = {row.franchise_id: row for row in allplay.all_play_week(season, 1)}
    assert (rows["0001"].wins, rows["0001"].losses, rows["0001"].ties) == (3, 0, 0)
    assert (rows["0003"].wins, rows["0003"].losses, rows["0003"].ties) == (2, 1, 0)
    assert (rows["0002"].wins, rows["0002"].losses, rows["0002"].ties) == (1, 2, 0)
    assert (rows["0004"].wins, rows["0004"].losses, rows["0004"].ties) == (0, 3, 0)
    assert rows["0001"].expected_wins == 1.0
    assert round(rows["0003"].expected_wins, 4) == 0.6667
    assert rows["0003"].record == "2-1-0"


def test_playoff_weeks_and_empty_weeks_produce_no_rows():
    season = four_team_league().season(2020)
    assert [row.week for row in allplay.all_play_weeks(season)] == [1, 1, 1, 1, 2, 2, 2, 2]
    assert allplay.all_play_week(season, 3) == []  # playoff week
    assert allplay.all_play_week(season, 9) == []  # no such week
    assert allplay.regular_weeks(season) == [1, 2]
    assert allplay.regular_weeks(season, through_week=1) == [1]


def test_ties_count_half():
    season = build_season(
        2020, PLAYERS,
        {1: [(lineup("0001", {"a1": 10.0}), lineup("0002", {"a2": 10.0}))]},
        last_regular_season_week=1, franchises=("0001", "0002"),
    )
    rows = allplay.all_play_week(season, 1)
    assert [(r.wins, r.losses, r.ties, r.expected_wins) for r in rows] == [(0, 0, 1, 0.5), (0, 0, 1, 0.5)]
    line = {s.franchise_id: s for s in allplay.standings(League.build([season]), season)}["0001"]
    assert (line.wins, line.losses, line.ties, line.allplay, line.expected_wins, line.luck) == (0, 0, 1, (0, 0, 1), 0.5, 0.0)


def test_season_standings_with_all_play_and_luck():
    league = four_team_league()
    lines = allplay.standings(league, league.season(2020))
    assert [line.name for line in lines] == ["Gamma", "Alpha", "Delta", "Beta"]
    by_id = {line.franchise_id: line for line in lines}
    alpha = by_id["0001"]
    assert (alpha.wins, alpha.losses, alpha.ties, alpha.points_for, alpha.points_against) == (1, 1, 0, 32.0, 28.0)
    assert (alpha.allplay, alpha.expected_wins, alpha.luck) == ((5, 1, 0), 1.67, -0.7)
    assert (alpha.record, alpha.allplay_record, round(alpha.allplay_pct, 3), alpha.games) == ("1-1-0", "5-1-0", 0.833, 2)
    assert (by_id["0003"].allplay, by_id["0003"].expected_wins, by_id["0003"].luck) == ((5, 1, 0), 1.67, 0.3)
    assert (by_id["0002"].allplay, by_id["0002"].expected_wins, by_id["0002"].luck) == ((1, 5, 0), 0.33, -0.3)
    assert (by_id["0004"].allplay, by_id["0004"].expected_wins, by_id["0004"].luck) == ((1, 5, 0), 0.33, 0.7)


def test_standings_through_an_earlier_week():
    league = four_team_league()
    lines = {s.franchise_id: s for s in allplay.standings(league, league.season(2020), through_week=1)}
    assert (lines["0001"].wins, lines["0001"].allplay, lines["0001"].expected_wins, lines["0001"].luck) == (1, (3, 0, 0), 1.0, 0.0)
    assert (lines["0003"].allplay, lines["0003"].luck) == ((2, 1, 0), 0.3)
    assert lines["0004"].points_for == 5.0


def test_franchises_without_a_game_still_get_a_line():
    league = four_team_league()
    lines = allplay.standings(league, league.season(2021))
    assert [line.name for line in lines] == ["Alpha Prime", "Beta", "Delta", "Gamma"]
    gamma = lines[3]
    assert (gamma.games, gamma.allplay, gamma.expected_wins, gamma.luck) == (0, (0, 0, 0), 0.0, 0.0)
    assert (lines[0].allplay, lines[0].expected_wins, lines[0].luck) == ((1, 0, 0), 1.0, 0.0)
