import pytest
from synthetic import four_team_league

from hof.stats import careers, milestones, records


@pytest.fixture(scope="module")
def league():
    return four_team_league()


@pytest.fixture(scope="module")
def tables(league):
    return records.records_book(league, careers.careers(league))


def test_high_score_and_top_starter(league, tables):
    facts = milestones.recap_facts(league, tables, (2020, 4))
    assert (facts.year, facts.week, facts.playoff) == (2020, 4, True)
    assert facts.high_score == ("Alpha", 30.0)
    assert facts.top_starter == ("QB A1", "Alpha", 30.0, 10.0)


def test_new_records_name_the_table_and_rank(league, tables):
    facts = milestones.recap_facts(league, tables, (2020, 4))
    assert "Alpha — 30.0 pts (Most points, game, #1)" in facts.new_records
    assert "QB A1 — 30.0 pts (Most points as a starter, game, #1)" in facts.new_records
    assert "Alpha — 50.0 pts (Highest-scoring final, #1)" in facts.new_records
    assert not any("season" in line.lower() for line in facts.new_records)


def test_milestones_use_cumulative_totals_before_and_after_the_week(league, tables):
    facts = milestones.recap_facts(league, tables, (2020, 3), point_step=50, start_step=3)
    assert facts.milestones == (
        "QB A1 passed 50 career points as a starter (Alpha)",
        "QB A1 made career start number 3 (Alpha)",
        "QB A2 made career start number 3 (Beta)",
        "QB A3 passed 50 career points as a starter (Gamma)",
        "QB A3 made career start number 3 (Gamma)",
        "QB A4 made career start number 3 (Delta)",
    )
    assert milestones.recap_facts(league, tables, (2020, 4), point_step=500, start_step=100).milestones == ()


def test_series_firsts(league, tables):
    final = milestones.recap_facts(league, tables, (2020, 4))
    assert final.series_firsts == ("Alpha beat Gamma for the first time ever (series now 1-1-0)",)
    assert milestones.recap_facts(league, tables, (2021, 1)).series_firsts == ()  # beat Beta last season too


def test_playoff_picture_in_the_regular_season(league, tables):
    facts = milestones.recap_facts(league, tables, (2020, 2))
    assert facts.playoff_picture == ("1. Gamma 2-0-0", "2. Alpha 1-1-0", "3. Delta 1-1-0", "4. Beta 0-2-0")
    assert facts.bracket == ()


def test_bracket_summary_in_playoff_weeks(league, tables):
    facts = milestones.recap_facts(league, tables, (2020, 3))
    assert facts.playoff_picture == ()
    assert facts.bracket == (
        "Semifinal: Gamma 20.0, Beta 10.0",
        "Semifinal: Alpha 25.0, Delta 5.0",
        "Next: Final, Gamma vs Alpha",
    )
    assert milestones.recap_facts(league, tables, (2020, 4)).bracket == ("Final: Alpha 30.0, Gamma 20.0",)


def test_season_awards(league, tables):
    awards = milestones.season_awards(league, tables, 2020)
    assert awards.top_scorer == ("QB A1", "Alpha", 87.0)
    assert awards.best_vor == ("QB A1", "Alpha", 48.0)
    assert awards.best_manager == ("Alpha", 1.0)
    assert awards.most_bench_left == ("Beta", 4.0)
    assert awards.champion == ("Alpha", "1-1-0", 32.0, 2)
    assert milestones.season_awards(league, tables, 2021).champion is None


def test_ordinal():
    assert [milestones.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 101)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "23rd", "101st",
    ]
