import pytest
from synthetic import four_team_league

from hof.stats import careers, records
from hof.stats.records import RecordEntry


@pytest.fixture(scope="module")
def book():
    league = four_team_league()
    tables = records.records_book(league, careers.careers(league))
    return {table.key: table for table in tables}


def test_every_spec_table_is_present_in_order():
    league = four_team_league()
    keys = [t.key for t in records.records_book(league, careers.careers(league))]
    assert keys == [
        "team_game_high", "team_game_low", "blowout", "closest", "loss_high", "win_low", "bench_left_game", "final_high",
        "team_season_high", "team_season_low", "record_best", "streak_win", "streak_loss", "bench_left_season", "efficiency_season",
        "player_game_high", "player_game_vor",
        "player_season_high", "player_season_vor", "player_season_starts",
        "career_points", "career_vor", "career_starts", "career_titles",
    ]


def test_team_single_game_records(book):
    assert book["team_game_high"].entries[0] == RecordEntry(30.0, "Alpha", "vs Gamma, 2020 Week 4 (Final)", 2020, 4, True, "0001", None)
    assert len(book["team_game_high"].entries) == 10
    assert book["team_game_low"].lowest_first is True
    assert book["team_game_low"].entries[0].value == 5.0
    assert book["blowout"].entries[0] == RecordEntry(20.0, "Alpha", "over Delta 25.0–5.0, 2020 Week 3 (Semifinal)", 2020, 3, True, "0001", None)
    assert book["closest"].entries[0].value == 2.0 and book["closest"].entries[0].holder == "Delta"
    assert book["loss_high"].entries[0] == RecordEntry(20.0, "Gamma", "lost to Alpha 30.0–20.0, 2020 Week 4 (Final)", 2020, 4, True, "0003", None)
    assert book["win_low"].entries[0] == RecordEntry(10.0, "Alpha Prime", "beat Beta 10.0–5.0, 2021 Week 1", 2021, 1, False, "0001", None)
    assert book["bench_left_game"].entries[0] == RecordEntry(4.0, "Beta", "10.0 of 14.0 possible, 2020 Week 1", 2020, 1, False, "0002", None)
    assert book["final_high"].entries == (RecordEntry(50.0, "Alpha", "30.0–20.0 over Gamma, 2020", 2020, 4, True, "0001", None),)


def test_team_season_records_use_finished_seasons_only(book):
    assert book["team_season_high"].entries[0] == RecordEntry(33.0, "Gamma", "2020, 2-0-0", 2020, None, False, "0003", None)
    assert book["team_season_low"].entries[0].holder == "Delta"
    assert all(entry.year == 2020 for table in ("team_season_high", "team_season_low") for entry in book[table].entries)
    assert book["record_best"].entries[0] == RecordEntry(1.0, "Gamma", "2-0-0, 33.0 pts", 2020, None, False, "0003", None)
    assert book["streak_win"].entries[0] == RecordEntry(3, "Gamma", "2020", 2020, None, False, "0003", None)
    assert book["streak_loss"].entries[0] == RecordEntry(3, "Beta", "2020", 2020, None, False, "0002", None)
    assert book["bench_left_season"].entries[0] == RecordEntry(4.0, "Beta", "2020", 2020, None, False, "0002", None)
    beta = next(e for e in book["efficiency_season"].entries if e.franchise_id == "0002")
    assert beta.value == 0.879
    assert book["efficiency_season"].entries[0].value == 1.0


def test_player_records(book):
    assert book["player_game_high"].entries[0] == RecordEntry(30.0, "QB A1", "Alpha, 2020 Week 4 (Final)", 2020, 4, True, "0001", "a1")
    # Single-game vor across every week, using the two-thirds-rank baseline (see test_hof_franchises
    # and test_hof_vor): week1 pool [20,15,10,5] baseline 10.0 -> a1 10.0, a3 5.0; week2 pool
    # [18,12,11,9] baseline 11.0 -> a3 7.0, a1 1.0; week3 pool [25,20,10,5] baseline 10.0 -> a1
    # 15.0, a3 10.0; week4 pool [30,20] baseline 20.0 -> a1 10.0; 2021 week1 pool [10,5] baseline
    # 5.0 -> a1 5.0. a1's week-3 start (Semifinal) is the highest single-game vor in the league.
    assert book["player_game_vor"].entries[0] == RecordEntry(15.0, "QB A1", "Alpha, 2020 Week 3 (Semifinal)", 2020, 3, True, "0001", "a1")
    assert book["player_season_high"].entries[0] == RecordEntry(87.0, "QB A1", "Alpha, 2020", 2020, None, False, "0001", "a1")
    # a1's 2020 season vor is 36.0 (see test_hof_franchises), the highest of the four.
    assert book["player_season_vor"].entries[0].value == 36.0
    assert book["player_season_starts"].entries[0].value == 4
    assert book["career_points"].entries[0] == RecordEntry(97.0, "QB A1", "2020–2021", 2020, None, False, None, "a1")
    # a1's career vor is 41.0 (see test_hof_franchises), the highest of the four.
    assert book["career_vor"].entries[0].value == 41.0
    assert book["career_starts"].entries[0].value == 5
    assert book["career_titles"].entries[0] == RecordEntry(1, "QB A1", "2020–2021", 2020, None, False, None, "a1")


def test_new_entries_for_a_week(book):
    new = records.entries_from_week(list(book.values()), 2021, 1)
    assert {(table.key, entry.holder) for table, entry in new} >= {("win_low", "Alpha Prime"), ("team_game_low", "Beta")}
    assert all(entry.year == 2021 and entry.week == 1 for _, entry in new)
    assert all(table.group in ("Team, single game", "Player, single game") for table, _ in new)
