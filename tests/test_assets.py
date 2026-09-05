import logging

from bdfl.assets import format_dollars, format_player_name, player_label, render_asset
from bdfl.models import LeagueInfo, Player

LEAGUE = LeagueInfo(year=2026, name="BDFL", franchises={"0005": "Jeff Janis Fan Club"})
PLAYERS = {
    "13299": Player(id="13299", name="Kittle, George", team="SFO", position="TE"),
    "17463": Player(id="17463", name="Simpson, Ty", team="", position="QB"),
    "0151": Player(id="0151", name="Bills, Buffalo", team="BUF", position="TMWR"),
}


def test_format_player_name_swaps_last_first():
    assert format_player_name("Kittle, George") == "George Kittle"
    assert format_player_name("Bills, Buffalo") == "Buffalo Bills"
    assert format_player_name("Madonna") == "Madonna"


def test_player_label_with_and_without_team():
    assert player_label(PLAYERS["13299"], "13299") == "George Kittle, SFO TE"
    assert player_label(PLAYERS["17463"], "17463") == "Ty Simpson, QB"
    assert player_label(None, "999") == "Unknown player (#999)"


def test_format_dollars():
    assert format_dollars("20") == "$20"
    assert format_dollars("3.00") == "$3"
    assert format_dollars("3.50") == "$3.50"
    assert format_dollars("abc") == "$abc"


def test_render_player_asset():
    assert render_asset("13299", LEAGUE, PLAYERS) == "George Kittle, SFO TE"
    assert render_asset("424242", LEAGUE, PLAYERS) == "Unknown player (#424242)"


def test_render_blind_bid_dollars():
    assert render_asset("BB_20", LEAGUE, PLAYERS) == "$20 blind bid dollars"


def test_render_future_pick_uses_franchise_name_and_one_based_round():
    assert render_asset("FP_0005_2027_3", LEAGUE, PLAYERS) == "Jeff Janis Fan Club 2027 Round 3 pick"
    assert render_asset("FP_0099_2027_1", LEAGUE, PLAYERS) == "Franchise 0099 2027 Round 1 pick"


def test_render_current_pick_is_zero_based_in_mfl():
    assert render_asset("DP_2_5", LEAGUE, PLAYERS) == "2026 Round 3 Pick 6"
    assert render_asset("DP_0_0", LEAGUE, PLAYERS) == "2026 Round 1 Pick 1"


def test_render_unknown_code_returns_raw_and_warns(caplog):
    with caplog.at_level(logging.WARNING):
        assert render_asset("XX_1", LEAGUE, PLAYERS) == "XX_1"
        assert render_asset("DP_a_b", LEAGUE, PLAYERS) == "DP_a_b"
    assert "unknown asset code" in caplog.text
