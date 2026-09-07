from synthetic import four_team_league

from hof.config import HallRules
from hof.snapshots import load_season
from hof.stats.model import compute


def test_compute_bundles_every_stat_for_the_synthetic_league():
    league = four_team_league()
    model = compute(league.seasons, HallRules(player_min_vor=40, player_min_starts=3, franchise_min_titles=1))
    assert model.through == (2021, 1)
    assert sorted(model.careers) == ["a1", "a2", "a3", "a4"]
    assert model.histories["0001"].totals.titles == 1
    assert len(model.records) == 24
    assert [p.player_id for p in model.hall.players] == ["a1"]
    assert model.drafts == [] and model.draft_rankings == [] and model.trades == []
    assert model.champions == [(2020, "0001", "0003")]


def test_compute_on_the_real_2020_fixture(fixtures_dir):
    season = load_season(fixtures_dir / "raw" / "2020")
    model = compute([season], HallRules())
    assert model.through == (2020, 16)
    assert model.champions == [(2020, "0010", "0002")]
    assert model.histories["0010"].totals.titles == 1
    assert model.histories["0010"].name == "Marcus Peters' Peter Peckers"
    assert len(model.careers) > 100
    assert all(career.starts >= 1 for career in model.careers.values())
    assert model.records[0].key == "team_game_high" and len(model.records[0].entries) == 10
    assert model.drafts[0].year == 2020 and len(model.drafts[0].picks) == 48
    assert len(model.trades) == 20
    assert all(len(line.sides) == 2 for line in model.trades)
    assert model.hall.players == ()  # one season cannot reach 400 value
