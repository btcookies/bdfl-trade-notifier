from synthetic import four_team_league

from hof.config import HallRules
from hof.snapshots import load_season
from hof.stats.model import compute


def test_compute_bundles_every_stat_for_the_synthetic_league():
    league = four_team_league()
    # a1's 2020 (finished-season) vor is 36.0, the only one of the four to clear 30 (a3's is
    # 22.0; see test_hof_franchises and test_hof_records for the arithmetic).
    model = compute(league.seasons, HallRules(player_min_vor=30, player_min_starts=3, franchise_min_titles=1))
    assert model.through == (2021, 1)
    assert sorted(model.careers) == ["a1", "a2", "a3", "a4"]
    assert model.histories["0001"].totals.titles == 1
    assert len(model.records) == 27
    assert [p.player_id for p in model.hall.players] == ["a1"]
    assert model.drafts == [] and model.draft_rankings == [] and model.trades == []
    assert model.champions == [(2020, "0001", "0003")]
    assert model.analytics[2020].awards_leaders == ("0001",)
    assert model.analytics[2021].final_power[0].name == "Alpha Prime"
    assert model.rivalries.order == ("0003", "0001", "0004", "0002")
    labelled = compute(league.seasons, HallRules(player_min_vor=30, player_min_starts=3, franchise_min_titles=1), {"high_score": "Big Number"})
    assert labelled.analytics[2020].weeks[0].awards[0].label == "Big Number"


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
    season = model.analytics[2020]
    # The fixture keeps weeklyResults for weeks 1 and 13 to 17 only; week 17 has no bracket game.
    assert [w.week for w in season.weeks] == [1, 13, 14, 15, 16] and season.power_week == 13
    assert season.weeks[1].power[0].rank == 1 and season.weeks[2].power == ()  # week 13 ranked, week 14 not
    week1 = season.weeks[0].standings
    assert len(week1) == 12 and sum(sum(line.allplay) for line in week1) == 132  # 12 franchises × 11 comparisons
    assert abs(sum(line.luck for line in season.standings)) < 0.6  # raw luck sums to zero; per-line rounding drifts at most 0.05 each
    assert len(season.weeks[0].awards) == 9  # a real week has a benched scorer
    cells = model.rivalries.cells
    assert len(model.rivalries.order) == 12
    assert all(cells[(a, b)][0] == cells[(b, a)][1] for (a, b) in cells)  # symmetric
