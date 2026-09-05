from bdfl.messages import (
    MAX_DESCRIPTION,
    chunk_entries,
    trade_details,
    trade_embed,
    trade_summary,
    waiver_details,
    waiver_messages,
    waiver_summary,
)
from bdfl.models import LeagueInfo, Player, Trade, WaiverClaim

LEAGUE = LeagueInfo(
    year=2026,
    name="Barbara Dodson's Fantasy League",
    franchises={"0011": "A.J. Mudbone", "0005": "Jeff Janis Fan Club", "0003": "The Youth Academy"},
)
PLAYERS = {
    "13299": Player("13299", "Kittle, George", "SFO", "TE"),
    "15255": Player("15255", "Gainwell, Kenneth", "TBB", "RB"),
    "15733": Player("15733", "Doe, John", "NYG", "WR"),
    "11247": Player("11247", "Ertz, Zach", "PHI", "TE"),
}


def make_trade(comments=""):
    return Trade(
        timestamp=1788400073,
        franchise1="0011",
        franchise2="0005",
        gave_up1=("15255", "13299"),
        gave_up2=("BB_20", "FP_0005_2027_3"),
        comments=comments,
        raw={},
    )


def make_claim(franchise="0003", added="15733", dropped=None, timestamp=1788339600, parsed=True):
    return WaiverClaim(
        timestamp=timestamp,
        franchise=franchise,
        added=added,
        bid="3.00",
        dropped=dropped,
        parsed=parsed,
        raw={"transaction": "garbage"},
    )


def test_trade_details_and_summary():
    details = trade_details(make_trade("Go Birds"), LEAGUE, PLAYERS)
    assert details == {
        "sides": [
            {
                "franchise_id": "0011",
                "franchise_name": "A.J. Mudbone",
                "assets": ["Kenneth Gainwell, TBB RB", "George Kittle, SFO TE"],
            },
            {
                "franchise_id": "0005",
                "franchise_name": "Jeff Janis Fan Club",
                "assets": ["$20 blind bid dollars", "Jeff Janis Fan Club 2027 Round 3 pick"],
            },
        ],
        "comments": "Go Birds",
    }
    assert trade_summary(details) == (
        "A.J. Mudbone gives up: Kenneth Gainwell, TBB RB, George Kittle, SFO TE | "
        "Jeff Janis Fan Club gives up: $20 blind bid dollars, Jeff Janis Fan Club 2027 Round 3 pick"
    )


def test_trade_embed_layout():
    trade = make_trade("Go Birds")
    embed = trade_embed(trade, trade_details(trade, LEAGUE, PLAYERS), LEAGUE)
    assert embed == {
        "title": "🚨 Trade Completed",
        "color": 0xE74C3C,
        "description": "Go Birds",
        "fields": [
            {
                "name": "A.J. Mudbone gives up",
                "value": "• Kenneth Gainwell, TBB RB\n• George Kittle, SFO TE",
                "inline": False,
            },
            {
                "name": "Jeff Janis Fan Club gives up",
                "value": "• $20 blind bid dollars\n• Jeff Janis Fan Club 2027 Round 3 pick",
                "inline": False,
            },
        ],
        "footer": {"text": "MFL · Barbara Dodson's Fantasy League · 2026"},
        "timestamp": "2026-09-03T01:47:53+00:00",
    }


def test_trade_embed_without_comments_and_with_empty_side():
    trade = Trade(1788400073, "0011", "0005", (), ("13299",), "", {})
    embed = trade_embed(trade, trade_details(trade, LEAGUE, PLAYERS), LEAGUE)
    assert "description" not in embed
    assert embed["fields"][0]["value"] == "• (nothing)"


def test_trade_embed_truncates_long_comments():
    trade = make_trade("x" * 2000)
    embed = trade_embed(trade, trade_details(trade, LEAGUE, PLAYERS), LEAGUE)
    assert len(embed["description"]) == 1000
    assert embed["description"].endswith("…")


def test_waiver_details_and_summary():
    details = waiver_details(make_claim(dropped="11247"), LEAGUE, PLAYERS)
    assert details == {
        "franchise_id": "0003",
        "franchise_name": "The Youth Academy",
        "bid": "$3",
        "added": "John Doe, NYG WR",
        "dropped": "Zach Ertz, PHI TE",
    }
    assert waiver_summary(details) == (
        "The Youth Academy won John Doe, NYG WR for $3, dropped Zach Ertz, PHI TE"
    )


def test_unparsed_waiver_details_and_summary():
    details = waiver_details(make_claim(added="", parsed=False), LEAGUE, PLAYERS)
    assert details["added"] is None
    assert details["raw_transaction"] == "garbage"
    assert waiver_summary(details) == "unparsed waiver: The Youth Academy garbage"


def test_waiver_messages_single_embed_sorted_by_time_then_franchise():
    later = make_claim(franchise="0011", added="13299", timestamp=1788339700)
    first = make_claim(franchise="0005", added="15255", dropped="11247")
    second = make_claim(franchise="0003", added="15733")
    items = [(later, waiver_details(later, LEAGUE, PLAYERS)),
             (first, waiver_details(first, LEAGUE, PLAYERS)),
             (second, waiver_details(second, LEAGUE, PLAYERS))]
    [(embeds, claims)] = waiver_messages(items, LEAGUE)
    assert claims == [first, second, later]
    assert embeds == [{
        "title": "✅ Waiver Claims Processed",
        "color": 0x2ECC71,
        "description": (
            "**Jeff Janis Fan Club** won **Kenneth Gainwell, TBB RB** for $3 · dropped Zach Ertz, PHI TE\n"
            "**The Youth Academy** won **John Doe, NYG WR** for $3\n"
            "**A.J. Mudbone** won **George Kittle, SFO TE** for $3"
        ),
        "footer": {"text": "MFL · Barbara Dodson's Fantasy League · 2026"},
        "timestamp": "2026-09-02T09:01:40+00:00",
    }]


def test_waiver_messages_unparsed_line():
    claim = make_claim(added="", parsed=False)
    [(embeds, _)] = waiver_messages([(claim, waiver_details(claim, LEAGUE, PLAYERS))], LEAGUE)
    assert embeds[0]["description"] == "**The Youth Academy** claim could not be parsed: `garbage`"


def test_waiver_messages_split_across_embeds_and_messages():
    # Each line is ~54 chars, so ~75 fit per 4096-char embed; 1200 claims need 16 embeds,
    # which is more than the 10 allowed per message, so two messages.
    items = []
    for i in range(1200):
        claim = make_claim(added="15733", timestamp=1788339600 + i)
        items.append((claim, waiver_details(claim, LEAGUE, PLAYERS)))
    messages = waiver_messages(items, LEAGUE)
    assert len(messages) == 2
    assert len(messages[0][0]) == 10
    assert all(len(e["description"]) <= MAX_DESCRIPTION for embeds, _ in messages for e in embeds)
    assert messages[0][0][0]["title"].startswith("✅ Waiver Claims Processed (1/")
    assert sum(len(claims) for _, claims in messages) == 1200
    assert [c for _, claims in messages for c in claims] == [c for c, _ in items]


def test_chunk_entries_respects_limit_and_newlines():
    entries = [("a", "xxxx"), ("b", "yyyy"), ("c", "zz")]
    assert chunk_entries(entries, limit=9) == [[("a", "xxxx"), ("b", "yyyy")], [("c", "zz")]]
    assert chunk_entries(entries, limit=8) == [[("a", "xxxx")], [("b", "yyyy"), ("c", "zz")]]
    assert chunk_entries([], limit=9) == []
