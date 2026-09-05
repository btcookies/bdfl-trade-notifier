from bdfl.messages import (
    MAX_DESCRIPTION,
    MAX_MESSAGE_CHARS,
    chunk_entries,
    embed_length,
    escape_markdown,
    group_embeds,
    iso_timestamp,
    trade_details,
    trade_embed,
    trade_summary,
    truncate,
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
        "parsed": True,
        "bid": "$3",
        "added": "John Doe, NYG WR",
        "dropped": "Zach Ertz, PHI TE",
    }
    assert waiver_summary(details) == (
        "The Youth Academy won John Doe, NYG WR for $3, dropped Zach Ertz, PHI TE"
    )


def test_unparsed_waiver_details_and_summary():
    details = waiver_details(make_claim(added="", parsed=False), LEAGUE, PLAYERS)
    assert details["parsed"] is False
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
    # Each line is ~54 chars, so 75 fit per 4096-char embed; 1200 claims need 16 embeds of
    # ~4049 chars each, and two of those blow the 6000-char per-message total, so 16 messages.
    items = []
    for i in range(1200):
        claim = make_claim(added="15733", timestamp=1788339600 + i)
        items.append((claim, waiver_details(claim, LEAGUE, PLAYERS)))
    messages = waiver_messages(items, LEAGUE)
    assert len(messages) == 16
    assert all(len(embeds) == 1 for embeds, _ in messages)
    assert all(sum(embed_length(e) for e in embeds) <= MAX_MESSAGE_CHARS for embeds, _ in messages)
    assert all(len(e["description"]) <= MAX_DESCRIPTION for embeds, _ in messages for e in embeds)
    assert [e["title"] for embeds, _ in messages for e in embeds] == [
        f"✅ Waiver Claims Processed ({i}/16)" for i in range(1, 17)
    ]
    assert sum(len(claims) for _, claims in messages) == 1200
    assert [c for _, claims in messages for c in claims] == [c for c, _ in items]


def test_chunk_entries_respects_limit_and_newlines():
    entries = [("a", "xxxx"), ("b", "yyyy"), ("c", "zz")]
    assert chunk_entries(entries, limit=9) == [[("a", "xxxx"), ("b", "yyyy")], [("c", "zz")]]
    assert chunk_entries(entries, limit=8) == [[("a", "xxxx")], [("b", "yyyy"), ("c", "zz")]]
    assert chunk_entries([], limit=9) == []


def test_escape_markdown():
    assert escape_markdown("The_Youth_Academy") == "The\\_Youth\\_Academy"
    assert escape_markdown("*A* ~B~ `C` |D| >E \\F") == "\\*A\\* \\~B\\~ \\`C\\` \\|D\\| \\>E \\\\F"
    assert escape_markdown("A.J. Mudbone") == "A.J. Mudbone"


def test_embeds_escape_markdown_in_names_but_details_do_not():
    league = LeagueInfo(2026, "BDFL", {"0011": "The_Youth_Academy", "0005": "*Mudbone*", "0003": "x"})
    trade = make_trade()
    details = trade_details(trade, league, PLAYERS)
    assert details["sides"][0]["franchise_name"] == "The_Youth_Academy"
    embed = trade_embed(trade, details, league)
    assert embed["fields"][0]["name"] == "The\\_Youth\\_Academy gives up"
    assert embed["fields"][1]["name"] == "\\*Mudbone\\* gives up"
    claim = make_claim(franchise="0011")
    wd = waiver_details(claim, league, PLAYERS)
    assert wd["franchise_name"] == "The_Youth_Academy"
    [(embeds, _)] = waiver_messages([(claim, wd)], league)
    assert embeds[0]["description"].startswith("**The\\_Youth\\_Academy** won")


def test_group_embeds_packs_by_count_and_budget():
    small = [({"title": "t", "description": "x" * 100}, [i]) for i in range(25)]
    grouped = group_embeds(small)
    assert [len(embeds) for embeds, _ in grouped] == [10, 10, 5]
    assert [items for _, items in grouped] == [list(range(10)), list(range(10, 20)), list(range(20, 25))]
    big = [({"title": "t", "description": "x" * 3000}, [i]) for i in range(3)]
    assert [len(embeds) for embeds, _ in group_embeds(big)] == [1, 1, 1]
    assert group_embeds([]) == []


def test_embed_length_counts_all_billable_text():
    embed = {"title": "ab", "description": "cde", "fields": [{"name": "fg", "value": "hij"}],
             "footer": {"text": "kl"}, "author": {"name": "m"}}
    assert embed_length(embed) == 13


def test_waiver_messages_empty_returns_empty():
    assert waiver_messages([], LEAGUE) == []


def test_chunk_entries_truncates_oversized_entry():
    chunks = chunk_entries([("a", "x" * 20), ("b", "yy")], limit=9)
    assert [len("\n".join(t for _, t in c)) for c in chunks] == [9, 2]
    assert chunks[0][0][1].endswith("…")


def test_trade_embed_truncates_long_field_name_and_value():
    league = LeagueInfo(2026, "BDFL", {"0011": "N" * 300, "0005": "B"})
    trade = Trade(1788400073, "0011", "0005", tuple(str(i) for i in range(200)), (), "", {})
    embed = trade_embed(trade, trade_details(trade, league, {}), league)
    assert len(embed["fields"][0]["name"]) == 256
    assert len(embed["fields"][0]["value"]) == 1024
    assert embed["fields"][0]["value"].endswith("…")
    assert embed_length(embed) <= MAX_MESSAGE_CHARS


def test_unparsed_line_uses_code_span_without_escapes():
    claim = make_claim(added="", parsed=False)
    claim = WaiverClaim(claim.timestamp, claim.franchise, "", "", None, False, {"transaction": "13299,|3.00|`x"})
    [(embeds, _)] = waiver_messages([(claim, waiver_details(claim, LEAGUE, PLAYERS))], LEAGUE)
    assert embeds[0]["description"] == "**The Youth Academy** claim could not be parsed: `13299,|3.00|'x`"


def test_truncate_does_not_end_on_dangling_backslash():
    assert truncate("abc\\de", 5) == "abc…"
    assert truncate("abcd\\", 5) == "abcd\\"


def test_escape_markdown_escapes_masked_links():
    assert escape_markdown("[click](https://x)") == "\\[click\\](https://x)"


def test_iso_timestamp_returns_none_for_absurd_epoch():
    assert iso_timestamp(99999999999999) is None
    trade = Trade(99999999999999, "0011", "0005", (), (), "", {})
    assert "timestamp" not in trade_embed(trade, trade_details(trade, LEAGUE, PLAYERS), LEAGUE)
