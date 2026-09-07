import pytest
from synthetic import four_team_league

from bdfl.messages import embed_length
from hof.config import HallRules
from hof.discord import wrap
from hof.stats import milestones
from hof.stats.model import compute

SITE = "https://example.test/hof/"


@pytest.fixture(scope="module")
def model():
    return compute(four_team_league().seasons, HallRules(player_min_vor=30, player_min_starts=3, franchise_min_titles=1))


def test_wrap_embed_for_2020(model):
    awards = milestones.season_awards(model.league, model.records, 2020)
    embed = wrap.wrap_embed(model, 2020, awards, SITE)
    assert embed["title"] == "🏆 2020 season wrap"
    assert embed["color"] == 0xE5B80B
    assert embed["description"] == (
        "**Alpha** wins its 1st title, **30.0–20.0** over **Gamma**. "
        "Regular season 1-1-0, 32.0 points, the 2nd-highest season ever."
    )
    awards_field, hall_field = embed["fields"]
    assert awards_field["name"] == "Season awards"
    assert awards_field["value"].splitlines() == [
        "**Top starter:** QB A1, 87.0 pts (Alpha)",
        "**Best value over replacement:** QB A1, +36.0 VOR (Alpha)",
        "**Best lineup manager:** Alpha, 100.0% of optimal",
        "**Most points left on the bench:** Beta, 4.0",
    ]
    assert hall_field["name"] == "🏛 Hall of Fame · Class of 2020"
    assert hall_field["value"].splitlines() == [
        "**QB A1** (QB) · 5 starts, 97.0 pts, +41.0 VOR, 1 title as a starter",
        "**Alpha Prime** · 1 title",
    ]
    assert embed["footer"] == {"text": f"Full records: {SITE}"}
    assert embed_length(embed) < 6000


def test_wrap_without_inductees_or_final(model):
    awards = milestones.season_awards(model.league, model.records, 2021)
    embed = wrap.wrap_embed(model, 2021, awards, SITE)
    assert embed["description"] == "The season has no final yet."
    hall_field = embed["fields"][-1]
    assert hall_field["value"] == "No new inductees."
