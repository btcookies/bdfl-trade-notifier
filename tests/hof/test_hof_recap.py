import pytest
from synthetic import four_team_league

from bdfl.messages import MAX_FIELD_VALUE, embed_length
from hof.discord import recap
from hof.stats import careers, milestones, records

SITE = "https://example.test/hof/"


@pytest.fixture(scope="module")
def tables():
    league = four_team_league()
    return league, records.records_book(league, careers.careers(league))


def test_final_week_recap(tables):
    league, book = tables
    facts = milestones.recap_facts(league, book, (2020, 4))
    embed = recap.recap_embed(facts, SITE)
    assert embed["title"] == "📜 Week 4 in the record books"
    assert embed["color"] == 0xF1C40F
    assert embed["description"] == (
        "**Alpha** put up **30.0**, the week's high. "
        "**QB A1** (Alpha) was the top starter with **30.0** (+10.0 VOR)."
    )
    names = [field["name"] for field in embed["fields"]]
    assert names == ["Records & milestones", "Bracket"]
    assert "Alpha — 30.0 pts (Most points, game, #1)" in embed["fields"][0]["value"]
    assert "Alpha beat Gamma for the first time ever (series now 1-1-0)" in embed["fields"][0]["value"]
    assert embed["fields"][1]["value"] == "Final: Alpha 30.0, Gamma 20.0"
    assert embed["footer"] == {"text": f"Full records: {SITE} · through Week 4"}
    assert embed_length(embed) < 6000


def test_regular_season_recap_has_the_playoff_picture(tables):
    league, book = tables
    facts = milestones.recap_facts(league, book, (2020, 2))
    embed = recap.recap_embed(facts, SITE)
    names = [field["name"] for field in embed["fields"]]
    assert "Playoff picture" in names and "Bracket" not in names
    picture = next(f for f in embed["fields"] if f["name"] == "Playoff picture")
    assert picture["value"].startswith("1. Gamma 2-0-0\n2. Alpha 1-1-0")


def test_quiet_week_has_no_records_field():
    facts = milestones.RecapFacts(2020, 9, False, ("Alpha", 101.5), ("QB A1", "Alpha", 20.0, 3.0), (), (), (), ("1. Alpha 5-4-0",), ())
    embed = recap.recap_embed(facts, SITE)
    assert [f["name"] for f in embed["fields"]] == ["Playoff picture"]


def test_markdown_in_names_is_escaped():
    facts = milestones.RecapFacts(2020, 1, False, ("Team_*Underscore*", 90.0), ("A_B", "C*D", 10.0, 1.0), ("Team_*Underscore* — 90.0 pts (Most points, game, #7)",), (), (), (), ())
    embed = recap.recap_embed(facts, SITE)
    assert "**Team\\_\\*Underscore\\***" in embed["description"]
    assert embed["fields"][0]["value"].startswith("Team\\_\\*Underscore\\*")


def test_fit_lines_drops_whole_lines_and_counts_the_rest():
    lines = [f"line {i} " + "x" * 290 for i in range(5)]  # about 300 characters each
    text = recap.fit_lines(lines, MAX_FIELD_VALUE)
    assert text.startswith("line 0") and "line 2" in text and "line 3" not in text
    assert text.endswith("…and 2 more")
    assert len(text) <= MAX_FIELD_VALUE
    assert recap.fit_lines(["short", "lines"], MAX_FIELD_VALUE) == "short\nlines"
    assert recap.fit_lines([], MAX_FIELD_VALUE) == ""
    long = recap.fit_lines(["y" * 2000, "z"], 100)
    assert len(long) <= 100 and long.endswith("…and 1 more")
