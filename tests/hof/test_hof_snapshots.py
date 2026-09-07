import json

import pytest

from hof.snapshots import load_all, load_season


def test_load_2020_fixture_season(fixtures_dir):
    season = load_season(fixtures_dir / "raw" / "2020")
    assert season.year == 2020
    assert season.league_id == "65522"
    assert season.complete is True
    assert season.name == "Barbara Dodson's Fantasy League"
    assert sorted(season.weeks) == [1, 13, 14, 15, 16, 17]
    assert len(season.bracket) == 5
    assert len(season.standings) == 12
    assert len(season.draft) == 48
    assert len(season.transactions.trades) == 20
    assert season.player("9099").position == "QB"
    assert season.bracket_info.teams_involved == 6
    assert season.bracket_rounds == 3


def test_counted_games_in_the_2020_fixture(fixtures_dir):
    season = load_season(fixtures_dir / "raw" / "2020")
    by_week = {}
    for game in season.games():
        by_week.setdefault(game.week, []).append(game)
    assert {week: len(games) for week, games in by_week.items()} == {1: 6, 13: 6, 14: 2, 15: 2, 16: 1}
    assert all(not g.playoff for g in by_week[1] + by_week[13])
    assert [g.round_name for g in by_week[14]] == ["First Round", "First Round"]
    assert [g.round_name for g in by_week[15]] == ["Semifinal", "Semifinal"]
    assert by_week[16][0].round_name == "Final"
    assert season.champion_id == "0010"
    assert season.final.margin == 3.7


def test_load_all_orders_seasons_and_skips_non_season_dirs(fixtures_dir, tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "notes").mkdir()
    for year in ("2021", "2020"):
        target = raw / year
        target.mkdir()
        for path in (fixtures_dir / "raw" / "2020").rglob("*.json"):
            dest = target / path.relative_to(fixtures_dir / "raw" / "2020")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(path.read_text())
    seasons = load_all(tmp_path)
    assert [s.year for s in seasons] == [2020, 2021]


def test_missing_files_load_as_empty(tmp_path):
    season_dir = tmp_path / "raw" / "2019"
    season_dir.mkdir(parents=True)
    (season_dir / "league.json").write_text(json.dumps({"league": {"name": "Sparse", "franchises": {"franchise": [{"id": "0001", "name": "A"}]}}}))
    season = load_season(season_dir)
    assert season.name == "Sparse"
    assert season.weeks == {}
    assert season.bracket == ()
    assert season.games() == []
    assert season.complete is False


def test_a_league_json_with_no_franchises_raises_instead_of_loading_wrong(tmp_path):
    """league.json is the only source of franchise identity and week boundaries; a season built
    on a missing/corrupt one would otherwise look valid while silently using wrong defaults."""
    season_dir = tmp_path / "raw" / "2019"
    season_dir.mkdir(parents=True)
    (season_dir / "league.json").write_text("{ not valid json")
    with pytest.raises(ValueError, match="no franchises"):
        load_season(season_dir)


def test_an_unpadded_week_filename_is_skipped_with_a_warning(tmp_path, caplog):
    season_dir = tmp_path / "raw" / "2019"
    (season_dir / "weeklyResults").mkdir(parents=True)
    (season_dir / "league.json").write_text(
        json.dumps({"league": {"name": "Sparse", "franchises": {"franchise": [{"id": "0001", "name": "A"}]}}})
    )
    (season_dir / "weeklyResults" / "W1.json").write_text("{}")
    with caplog.at_level("WARNING"):
        season = load_season(season_dir)
    assert season.weeks == {}
    assert "unexpected file in weeklyResults" in caplog.text


def test_load_all_without_a_raw_dir(tmp_path):
    assert load_all(tmp_path) == []
