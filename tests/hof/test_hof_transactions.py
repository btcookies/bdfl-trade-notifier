import json

import pytest

from hof.model.transactions import (
    FreeAgentMove,
    RosterMove,
    Trade,
    TransactionLog,
    WaiverClaim,
    parse_transactions,
)


@pytest.fixture
def log_2020(fixtures_dir) -> TransactionLog:
    body = json.loads((fixtures_dir / "raw" / "2020" / "transactions.json").read_text())
    return parse_transactions(body)


def test_counts_by_type_match_the_2020_log(log_2020):
    assert len(log_2020.trades) == 20
    assert len(log_2020.waivers) == 97
    assert len(log_2020.free_agents) == 147
    assert len(log_2020.roster_moves) == 288
    assert len(log_2020.lock_times) == 17


def test_entries_are_sorted_by_timestamp(log_2020):
    for group in (log_2020.trades, log_2020.waivers, log_2020.free_agents, log_2020.roster_moves):
        stamps = [entry.timestamp for entry in group]
        assert stamps == sorted(stamps)
    assert list(log_2020.lock_times) == sorted(log_2020.lock_times)


def test_first_2020_trade(log_2020):
    first = log_2020.trades[0]
    assert first == Trade(
        timestamp=1594133412,
        franchise1="0001",
        franchise2="0008",
        gave_up1=("DP_0_10", "DP_1_11", "FP_0001_2021_2"),
        gave_up2=("DP_0_4",),
        comments="",
    )


def test_effective_week_uses_lock_timestamps(log_2020):
    first_lock, second_lock = log_2020.lock_times[0], log_2020.lock_times[1]
    assert log_2020.effective_week(first_lock - 1, start_week=1) == 1
    assert log_2020.effective_week(first_lock, start_week=1) == 2
    assert log_2020.effective_week(second_lock - 1, start_week=1) == 2
    assert log_2020.effective_week(log_2020.lock_times[-1], start_week=1) is None
    assert log_2020.week_locked_at(1, start_week=1) == first_lock
    assert log_2020.week_locked_at(99, start_week=1) is None


def test_parses_each_transaction_shape():
    body = {
        "transactions": {
            "transaction": [
                {"type": "BBID_WAIVER", "timestamp": "10", "franchise": "0003", "transaction": "14209,|1.00|"},
                {"type": "BBID_WAIVER", "timestamp": "11", "franchise": "0003", "transaction": "1,|2.50|2,"},
                {"type": "FREE_AGENT", "timestamp": "12", "franchise": "0003", "transaction": "|13133,"},
                {"type": "FREE_AGENT", "timestamp": "13", "franchise": "0004", "transaction": "5,6,|7,"},
                {"type": "IR", "timestamp": "14", "franchise": "0008", "activated": "11783,", "deactivated": "11182,"},
                {"type": "TAXI", "timestamp": "15", "franchise": "0006", "promoted": "", "demoted": "14087,"},
                {"type": "LOCK_ALL_PLAYERS", "timestamp": "20", "franchise": ""},
                {"type": "UNLOCK_ALL_PLAYERS", "timestamp": "30", "franchise": ""},
                {"type": "BBID_AUTO_PROCESS_WAIVERS", "timestamp": "31", "franchise": ""},
                {"type": "TRADE", "timestamp": "not a number", "franchise": "0001", "franchise2": "0002"},
            ]
        }
    }
    log = parse_transactions(body)
    assert log.waivers == (
        WaiverClaim(10, "0003", "14209", "1.00", None),
        WaiverClaim(11, "0003", "1", "2.50", "2"),
    )
    assert log.free_agents == (
        FreeAgentMove(12, "0003", (), ("13133",)),
        FreeAgentMove(13, "0004", ("5", "6"), ("7",)),
    )
    assert log.roster_moves == (
        RosterMove(14, "0008", "IR", ("11182",), ("11783",)),
        RosterMove(15, "0006", "TAXI", ("14087",), ()),
    )
    assert log.lock_times == (20,)
    assert log.trades == ()


def test_an_empty_transactions_element_does_not_crash():
    """MFL's JSON mode can return "" for an empty transaction child; a preseason or
    early-season fetch (e.g. the current, in-progress season) may have no transactions yet."""
    assert parse_transactions({"transactions": {"transaction": ""}}) == TransactionLog((), (), (), (), ())
    assert parse_transactions({"transactions": ""}) == TransactionLog((), (), (), (), ())
