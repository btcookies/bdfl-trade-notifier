from dataclasses import replace

from synthetic import four_team_league

from hof.model.season import DraftPick
from hof.stats import careers, drafts
from hof.stats.drafts import DraftRanking, PickLine
from hof.stats.league import League

PICKS = (
    DraftPick(1, 1, "0001", "a1", 10),
    DraftPick(1, 2, "0003", "a3", 11, "[Pick traded from Beta.]"),
    DraftPick(2, 1, "0002", "a2", 12, "Pick made by Commissioner."),
    DraftPick(2, 2, "0004", "a4", 13, "[Pick traded from D.K. Nobody.\nPick made by Commissioner.]"),
)


def league_with_draft():
    base = four_team_league()
    s2020 = replace(base.season(2020), draft=PICKS)
    return League.build([s2020, base.season(2021)])


def test_chain_parsing_handles_brackets_periods_and_missing_lines():
    assert drafts.chain("[Pick traded from Suck My Ditka.\nPick traded from D.K. Mudbone.\nPick made by Commissioner.]") == ["Suck My Ditka", "D.K. Mudbone"]
    assert drafts.chain("Pick traded from Free hernandez.") == ["Free hernandez"]
    assert drafts.chain("[Pick made from Pre-Draft List]") == []
    assert drafts.chain("") == []


def test_original_owner_is_the_first_chain_name_or_the_drafter():
    league = league_with_draft()
    by_name = league.franchise_by_name()
    assert drafts.original_owner(PICKS[0], by_name) == "0001"
    assert drafts.original_owner(PICKS[1], by_name) == "0002"
    assert drafts.original_owner(PICKS[2], by_name) == "0002"
    assert drafts.original_owner(PICKS[3], by_name) is None


def test_summaries_credit_value_for_the_drafting_franchise():
    league = league_with_draft()
    summaries = drafts.draft_summaries(league, careers.careers(league))
    assert [s.year for s in summaries] == [2020]
    summary = summaries[0]
    assert (summary.rounds, summary.startup) == (2, False)
    # a1's career vor is 41.0 (two-thirds-rank QB pool baselines: see test_hof_franchises --
    # 10.0 + 1.0 + 15.0 + 10.0 in 2020, + 5.0 in 2021 week 1); a1 played only for 0001, so
    # vor_for as a starter for the drafting franchise equals the full career total.
    assert summary.picks[0] == PickLine(2020, 1, 1, "0001", "Alpha", "0001", "a1", "QB A1", "QB", 5, 97.0, 41.0, 97.0, 41.0)
    assert summary.picks[1].original_owner_id == "0002"
    assert summary.picks[3].original_owner_id is None
    # a3 played only for 0003 all four 2020 starts: vor 5.0 + 7.0 + 10.0 + 0.0 = 22.0.
    assert (summary.picks[1].starts_for, summary.picks[1].vor_for) == (4, 22.0)
    # a2's career vor: 0.0 + -2.0 + 0.0 (2020) + 0.0 (2021 week 1) = -2.0.
    # a4's career vor: -5.0 + 0.0 + -5.0 (2020, no week-4 start; eliminated in the first round) = -10.0.
    # steal = best vor_for outside round one: a2's -2.0 beats a4's -10.0.
    assert summary.steal.player_id == "a2"
    # bust = worst vor_for in round one: a3's 22.0 is worse than a1's 41.0.
    assert summary.bust.player_id == "a3"


def test_rankings_sum_value_by_drafting_franchise():
    league = league_with_draft()
    summaries = drafts.draft_summaries(league, careers.careers(league))
    # Each franchise made exactly one pick, so its ranking vor is that player's career vor:
    # a1 41.0, a3 22.0, a2 -2.0, a4 -10.0, same relative order as before.
    assert drafts.draft_rankings(league, summaries) == [
        DraftRanking("0001", "Alpha Prime", 1, 41.0),
        DraftRanking("0003", "Gamma", 1, 22.0),
        DraftRanking("0002", "Beta", 1, -2.0),
        DraftRanking("0004", "Delta", 1, -10.0),
    ]


def test_startup_draft_and_empty_rounds():
    league = league_with_draft()
    big = tuple(DraftPick(r, 1, "0001", "a1", r) for r in range(1, 13))
    season = replace(league.season(2020), draft=big)
    summaries = drafts.draft_summaries(League.build([season]), careers.careers(League.build([season])))
    assert summaries[0].startup is True
    assert summaries[0].bust.round == 1
    assert summaries[0].steal.round == 2
    empty = drafts.draft_summaries(League.build([replace(season, draft=())]), {})
    assert empty == []
