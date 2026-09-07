from synthetic import build_season, lineup

from hof.model.season import BracketGame, DraftPick
from hof.model.transactions import Trade, TransactionLog
from hof.stats import careers, trades
from hof.stats.league import League
from hof.stats.trades import Asset, TradeSide

PLAYERS = {
    "q1": ("QB One", "QB"),
    "q2": ("QB Two", "QB"),
    "r1": ("RB One", "RB"),
    "r2": ("RB Two", "RB"),
    "rk2": ("Rookie Two", "RB"),
}
NAMES = {"0001": "Alpha", "0002": "Beta"}


def trade_league():
    """Four trades: a player for dollars (A), a future pick for a current-year pick (B), an
    offseason player swap that lands in the next season (C), and a pending one (D)."""
    log_2020 = TransactionLog(
        trades=(
            Trade(150, "0001", "0002", ("r1",), ("BB_5",), "cash grab"),
            Trade(160, "0002", "0001", ("FP_0002_2021_1",), ("DP_1_1",), ""),
            Trade(999, "0001", "0002", ("q1",), ("q2",), ""),
        ),
        waivers=(),
        free_agents=(),
        roster_moves=(),
        lock_times=(100, 200, 300),
    )
    s2020 = build_season(
        2020,
        PLAYERS,
        {
            1: [(lineup("0001", {"q1": 20.0, "r1": 10.0}), lineup("0002", {"q2": 15.0, "r2": 8.0}))],
            2: [(lineup("0002", {"q2": 12.0, "r1": 14.0, "r2": 3.0}), lineup("0001", {"q1": 9.0}))],
            3: [(lineup("0001", {"q1": 30.0}), lineup("0002", {"q2": 5.0, "r1": 7.0, "r2": 2.0}))],
        },
        last_regular_season_week=2,
        franchises=("0001", "0002"),
        bracket=(BracketGame(3, "1", 0, "0001", "0002", 1, 2),),
        transactions=log_2020,
        draft=(DraftPick(2, 2, "0002", "r2", 40),),
        names=NAMES,
    )
    log_2021 = TransactionLog(
        trades=(Trade(50, "0001", "0002", ("rk2",), ("q1",), ""),),
        waivers=(),
        free_agents=(),
        roster_moves=(),
        lock_times=(),
    )
    s2021 = build_season(
        2021,
        PLAYERS,
        {1: [(lineup("0002", {"q1": 20.0}), lineup("0001", {"q2": 5.0, "rk2": 9.0}))]},
        last_regular_season_week=2,
        franchises=("0001", "0002"),
        complete=False,
        transactions=log_2021,
        draft=(DraftPick(1, 1, "0001", "rk2", 60, "[Pick traded from Beta.]"),),
        names=NAMES,
    )
    return League.build([s2020, s2021])


def ledger():
    league = trade_league()
    return trades.trade_ledger(league, careers.stints(league))


def test_ledger_is_newest_first_with_effective_weeks():
    lines = ledger()
    assert [(line.year, line.timestamp) for line in lines] == [(2021, 50), (2020, 999), (2020, 160), (2020, 150)]
    assert [line.effective for line in lines] == [(2022, 0), (2021, 0), (2020, 2), (2020, 2)]
    assert [line.pending for line in lines] == [True, False, False, False]


def test_player_for_dollars_is_credited_by_stint_from_the_effective_week():
    line = ledger()[3]
    assert line.comments == "cash grab"
    assert line.sides == (
        TradeSide("0001", "Alpha", (Asset("BB_5", "dollars", "$5 blind-bid dollars", None, 0, 0.0, 0.0),), 0.0),
        TradeSide("0002", "Beta", (Asset("r1", "player", "RB One (RB)", "r1", 2, 21.0, 16.0),), 16.0),
    )
    assert line.verdict == "Ahead: Beta by 16.0"


def test_picks_resolve_to_players_and_credit_the_drafting_franchise():
    line = ledger()[2]
    beta, alpha = line.sides  # franchise1 of this trade is Beta, so it is listed first
    assert (beta.franchise_id, alpha.franchise_id) == ("0002", "0001")
    assert alpha.received == (Asset("FP_0002_2021_1", "future_pick", "Beta 2021 Round 1 pick → Rookie Two", "rk2", 1, 9.0, 0.0),)
    assert beta.received == (Asset("DP_1_1", "pick", "2020 Round 2 Pick 2 → RB Two", "r2", 3, 13.0, 0.0),)
    assert line.verdict == "Even"


def test_offseason_trade_lands_in_the_next_season():
    line = ledger()[1]
    alpha, beta = line.sides
    assert beta.received[0] == Asset("q1", "player", "QB One (QB)", "q1", 1, 20.0, 15.0)
    assert alpha.received[0] == Asset("q2", "player", "QB Two (QB)", "q2", 1, 5.0, 0.0)
    assert line.verdict == "Ahead: Beta by 15.0"


def test_pending_trade_has_no_values():
    line = ledger()[0]
    assert line.verdict == "Pending"
    assert all(asset.starts == 0 and asset.vor == 0.0 for side in line.sides for asset in side.received)
    assert line.sides[1].received[0].label == "Rookie Two (RB)"


def test_unresolvable_picks_keep_their_label():
    league = trade_league()
    by_name = league.franchise_by_name()
    assert trades.resolve_future_pick("FP_0002_2027_1", league, by_name) is None
    assert trades.resolve_future_pick("FP_0009_2021_1", league, by_name) is None
    assert trades.resolve_future_pick("FP_bad", league, by_name) is None
    assert trades.resolve_current_pick("DP_5_5", league.season(2020)) is None
    assert trades.resolve_current_pick("DP_x_y", league.season(2020)) is None
