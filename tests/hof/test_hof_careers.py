from synthetic import build_season, lineup

from hof.model.season import BracketGame, DraftPick
from hof.model.transactions import FreeAgentMove, Trade, TransactionLog, WaiverClaim
from hof.stats import careers
from hof.stats.league import League

PLAYERS = {
    "q1": ("QB One", "QB"),
    "q2": ("QB Two", "QB"),
    "r1": ("RB One", "RB"),
    "r2": ("RB Two", "RB"),
    "rk": ("Rookie Back", "RB"),
}
LOCKS = (100, 200, 300)  # weeks 1, 2, 3 lock at these timestamps


def league_with_moves():
    """2020: r1 starts on 0001, is traded to 0002 after week 1; rk is drafted by 0002 and claimed
    by 0001 on waivers before week 3; q2 is dropped after week 2. 2021: r1 stays on 0002."""
    log_2020 = TransactionLog(
        trades=(Trade(150, "0001", "0002", ("r1",), ("BB_5",), ""),),
        waivers=(WaiverClaim(250, "0001", "rk", "12.00", None),),
        free_agents=(FreeAgentMove(260, "0002", (), ("q2",)),),
        roster_moves=(),
        lock_times=LOCKS,
    )
    s2020 = build_season(
        2020,
        PLAYERS,
        {
            1: [(lineup("0001", {"q1": 20.0, "r1": 10.0}), lineup("0002", {"q2": 15.0, "r2": 8.0}, bench={"rk": 3.0}))],
            2: [(lineup("0002", {"q2": 12.0, "r1": 14.0}, bench={"rk": 6.0}), lineup("0001", {"q1": 9.0, "r2": 0.0}))],
            3: [(lineup("0001", {"q1": 30.0, "rk": 11.0}), lineup("0002", {"r1": 7.0, "r2": 2.0}))],
        },
        last_regular_season_week=2,
        franchises=("0001", "0002"),
        bracket=(BracketGame(3, "1", 0, "0001", "0002", 1, 2),),
        transactions=log_2020,
        draft=(DraftPick(1, 1, "0002", "rk", 50),),
        names={"0001": "Alpha", "0002": "Beta"},
    )
    s2021 = build_season(
        2021,
        PLAYERS,
        {1: [(lineup("0002", {"r1": 20.0}), lineup("0001", {"q1": 5.0, "rk": 9.0}))]},
        last_regular_season_week=1,
        franchises=("0001", "0002"),
        complete=False,
        names={"0001": "Alpha", "0002": "Beta"},
    )
    return League.build([s2020, s2021])


def test_stints_follow_roster_membership_across_seasons():
    league = league_with_moves()
    stints = careers.stints(league)
    assert stints["r1"] == [
        careers.Stint("r1", "0001", (2020, 1), (2020, 1)),
        careers.Stint("r1", "0002", (2020, 2), (2021, 1)),
    ]
    assert stints["rk"] == [
        careers.Stint("rk", "0002", (2020, 1), (2020, 2)),
        careers.Stint("rk", "0001", (2020, 3), (2021, 1)),
    ]
    assert stints["q2"] == [careers.Stint("q2", "0002", (2020, 1), (2020, 2))]


def test_moves_are_matched_to_transactions_and_the_draft():
    league = league_with_moves()
    moves = {pid: c.moves for pid, c in careers.careers(league).items()}
    assert moves["r1"] == (
        careers.Move("joined", 2020, 1, "0001"),
        careers.Move("traded away", 2020, 1, "0001", "to Beta"),
        careers.Move("traded", 2020, 2, "0002", "from Alpha"),
    )
    assert moves["rk"] == (
        careers.Move("drafted", 2020, 1, "0002", "Round 1, Pick 1"),
        careers.Move("left", 2020, 2, "0002"),
        careers.Move("claimed", 2020, 3, "0001", "$12"),
    )
    assert moves["q2"] == (
        careers.Move("joined", 2020, 1, "0002"),
        careers.Move("dropped", 2020, 2, "0002"),
    )


def test_season_lines_and_career_totals():
    league = league_with_moves()
    r1 = careers.careers(league)["r1"]
    assert r1.name == "RB One" and r1.position == "RB"
    assert [line.year for line in r1.seasons] == [2020, 2021]
    line = r1.seasons[0]
    assert line.franchise_ids == ("0001", "0002")
    assert (line.starts, line.points) == (3, 31.0)
    assert (line.playoff_starts, line.playoff_points) == (1, 7.0)
    assert line.title is False
    assert r1.seasons[1].title is False
    assert (r1.starts, r1.points, r1.playoff_starts) == (4, 51.0, 1)
    assert r1.franchise_ids == ("0001", "0002")
    assert (r1.first_year, r1.last_year, r1.active) == (2020, 2021, True)
    q2 = careers.careers(league)["q2"]
    assert q2.active is False
    assert q2.last_year == 2020


def test_bench_points_and_titles():
    league = league_with_moves()
    rk = careers.careers(league)["rk"]
    assert rk.seasons[0].bench_points == 9.0  # 3.0 in week 1 plus 6.0 in week 2, both counted games
    assert rk.seasons[0].title is True  # started for 0001, the 2020 champion, in the final
    assert rk.titles == 1
    q1 = careers.careers(league)["q1"]
    assert q1.titles == 1
    assert careers.careers(league)["q2"].titles == 0


def test_players_without_a_start_are_excluded():
    league = league_with_moves()
    s = build_season(2022, {"b": ("Bench Only", "WR")}, {1: [(lineup("0001", {}, bench={"b": 5.0}), lineup("0002", {}))]}, 1, franchises=("0001", "0002"))
    league = League.build(league.seasons + [s])
    assert "b" not in careers.careers(league)


def test_effective_key_maps_offseason_trades_to_next_season():
    league = league_with_moves()
    season = league.season(2020)
    assert careers.effective_key(season, 150) == (2020, 2)
    assert careers.effective_key(season, 99) == (2020, 1)
    assert careers.effective_key(season, 999) == (2021, 0)
