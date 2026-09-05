from bdfl.models import (
    LeagueInfo,
    Trade,
    WaiverClaim,
    as_list,
    parse_transactions,
    referenced_player_ids,
)

TRADE = {
    "type": "TRADE",
    "timestamp": "1788400073",
    "franchise": "0011",
    "franchise2": "0005",
    "franchise1_gave_up": "15255,13299,",
    "franchise2_gave_up": "17463,BB_20,FP_0005_2027_3,DP_0_1,",
    "comments": "  deal done ",
    "expires": "1789004756",
    "by_commish": "1",
}

WAIVER = {
    "type": "BBID_WAIVER",
    "timestamp": "1788339600",
    "franchise": "0003",
    "transaction": "15733,|3.00|",
}

WAIVER_WITH_DROP = {
    "type": "BBID_WAIVER",
    "timestamp": "1788339600",
    "franchise": "0006",
    "transaction": "14209,|10.00|11247,",
}


def test_as_list_normalizes_none_dict_and_list():
    assert as_list(None) == []
    assert as_list({"a": 1}) == [{"a": 1}]
    assert as_list([1, 2]) == [1, 2]


def test_parse_trade():
    [trade] = parse_transactions({"transactions": {"transaction": [TRADE]}})
    assert isinstance(trade, Trade)
    assert trade.timestamp == 1788400073
    assert trade.franchise1 == "0011"
    assert trade.franchise2 == "0005"
    assert trade.gave_up1 == ("15255", "13299")
    assert trade.gave_up2 == ("17463", "BB_20", "FP_0005_2027_3", "DP_0_1")
    assert trade.comments == "deal done"
    assert trade.raw == TRADE
    assert trade.type == "TRADE"
    assert trade.key == "TRADE#1788400073#0011#0005"
    assert trade.franchise_ids == ["0011", "0005"]


def test_parse_waiver_without_drop():
    [claim] = parse_transactions({"transactions": {"transaction": [WAIVER]}})
    assert isinstance(claim, WaiverClaim)
    assert claim.parsed is True
    assert claim.timestamp == 1788339600
    assert claim.franchise == "0003"
    assert claim.added == "15733"
    assert claim.bid == "3.00"
    assert claim.dropped is None
    assert claim.type == "BBID_WAIVER"
    assert claim.key == "WAIVER#1788339600#0003#15733"
    assert claim.franchise_ids == ["0003"]


def test_parse_waiver_with_drop_and_trailing_comma():
    [claim] = parse_transactions({"transactions": {"transaction": [WAIVER_WITH_DROP]}})
    assert claim.added == "14209"
    assert claim.bid == "10.00"
    assert claim.dropped == "11247"


def test_parse_waiver_unparsable_is_kept_with_stable_key(caplog):
    import logging

    bad = {**WAIVER, "transaction": "garbage"}
    with caplog.at_level(logging.WARNING):
        [claim] = parse_transactions({"transactions": {"transaction": [bad]}})
    assert "unparsable waiver transaction" in caplog.text
    assert claim.parsed is False
    assert claim.added == ""
    assert claim.key.startswith("WAIVER#1788339600#0003#unparsed-")
    again = parse_transactions({"transactions": {"transaction": [bad]}})[0]
    assert again.key == claim.key


def test_parse_single_transaction_dict_and_ignores_other_types():
    payload = {"transactions": {"transaction": {**TRADE, "type": "IR"}}}
    assert parse_transactions(payload) == []
    payload = {"transactions": {"transaction": TRADE}}
    assert len(parse_transactions(payload)) == 1


def test_parse_empty_payloads():
    assert parse_transactions({}) == []
    assert parse_transactions({"transactions": {}}) == []
    assert parse_transactions({"transactions": {"transaction": []}}) == []


def test_referenced_player_ids_collects_only_numeric_codes_and_claim_players():
    records = parse_transactions(
        {"transactions": {"transaction": [TRADE, WAIVER, WAIVER_WITH_DROP]}}
    )
    assert referenced_player_ids(records) == {
        "15255", "13299", "17463", "15733", "14209", "11247"
    }


def test_league_info_franchise_name_fallback():
    league = LeagueInfo(year=2026, name="BDFL", franchises={"0001": "The Youth Academy"})
    assert league.franchise_name("0001") == "The Youth Academy"
    assert league.franchise_name("0099") == "Franchise 0099"


def test_malformed_records_are_skipped_and_good_ones_kept(caplog):
    import logging

    missing_franchise2 = {k: v for k, v in TRADE.items() if k != "franchise2"}
    bad_timestamp = {**TRADE, "timestamp": ""}
    missing_franchise = {k: v for k, v in WAIVER.items() if k != "franchise"}
    payload = {
        "transactions": {
            "transaction": [
                missing_franchise2, TRADE, bad_timestamp, "not a dict", missing_franchise, WAIVER
            ]
        }
    }
    with caplog.at_level(logging.WARNING):
        records = parse_transactions(payload)
    assert [r.key for r in records] == [
        "TRADE#1788400073#0011#0005", "WAIVER#1788339600#0003#15733"
    ]
    assert caplog.text.count("skipping unparsable transaction") == 4


def test_records_are_hashable_and_compare_on_parsed_fields():
    import dataclasses

    [a] = parse_transactions({"transactions": {"transaction": [TRADE]}})
    [b] = parse_transactions({"transactions": {"transaction": [{**TRADE, "expires": "0"}]}})
    assert a == b
    assert len({a, b}) == 1
    assert "type" not in {f.name for f in dataclasses.fields(Trade)}


def test_bid_must_be_numeric():
    bad = {**WAIVER, "transaction": "15733,|3.0.0|"}
    [claim] = parse_transactions({"transactions": {"transaction": [bad]}})
    assert claim.parsed is False
