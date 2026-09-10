import pytest
from synthetic import build_season, lineup

from hof.model.season import BracketGame
from hof.stats import franchises
from hof.stats.league import Era, League

PLAYERS = {f"a{i}": (f"QB A{i}", "QB") for i in range(1, 5)}
NAMES_2020 = {"0001": "Alpha", "0002": "Beta", "0003": "Gamma", "0004": "Delta"}
NAMES_2021 = {**NAMES_2020, "0001": "Alpha Prime"}


def league():
    s2020 = build_season(
        2020,
        PLAYERS,
        {
            1: [(lineup("0001", {"a1": 20.0}), lineup("0002", {"a2": 10.0})), (lineup("0003", {"a3": 15.0}), lineup("0004", {"a4": 5.0}))],
            2: [(lineup("0001", {"a1": 12.0}), lineup("0003", {"a3": 18.0})), (lineup("0002", {"a2": 9.0}), lineup("0004", {"a4": 11.0}))],
            3: [(lineup("0003", {"a3": 20.0}), lineup("0002", {"a2": 10.0})), (lineup("0001", {"a1": 25.0}), lineup("0004", {"a4": 5.0}))],
            4: [(lineup("0003", {"a3": 20.0}), lineup("0001", {"a1": 30.0}))],
        },
        last_regular_season_week=2,
        bracket=(
            BracketGame(3, "1", 0, "0003", "0002", 1, 4),
            BracketGame(3, "2", 0, "0001", "0004", 2, 3),
            BracketGame(4, "3", 1, "0003", "0001", 1, 2),
        ),
        names=NAMES_2020,
    )
    s2021 = build_season(
        2021,
        PLAYERS,
        {1: [(lineup("0001", {"a1": 10.0}), lineup("0002", {"a2": 5.0}))]},
        last_regular_season_week=2,
        complete=False,
        names=NAMES_2021,
    )
    return League.build([s2020, s2021])


def test_season_rows_record_finish_seed_and_top_starter():
    rows = {row.year: row for row in franchises.season_rows(league(), "0001")}
    r2020 = rows[2020]
    assert (r2020.name, r2020.wins, r2020.losses, r2020.ties) == ("Alpha", 1, 1, 0)
    assert (r2020.points_for, r2020.points_against) == (32.0, 28.0)
    assert (r2020.seed, r2020.playoff_wins, r2020.playoff_losses) == (2, 2, 0)
    assert (r2020.finish, r2020.title, r2020.in_progress) == ("Champion", True, False)
    # a1's 2020 vor is 10.0 (week1) + 1.0 (week2) + 15.0 (week3) + 10.0 (week4) = 36.0 -- QB pools
    # of 4 (weeks 1-2: baseline is the 3rd best), 4 (week 3, playoff, same), and 2 (week 4,
    # playoff final: baseline is the worse of the two, a3's own 20.0).
    # Week1 pool [20,15,10,5] -> baseline 10.0, a1 scored 20.0: vor 10.0.
    # Week2 pool [18,12,11,9] -> baseline 11.0, a1 scored 12.0: vor 1.0.
    # Week3 pool [25,20,10,5] -> baseline 10.0, a1 scored 25.0: vor 15.0.
    # Week4 pool [30,20] -> baseline 20.0 (worse of the two), a1 scored 30.0: vor 10.0.
    assert r2020.top_starter == ("a1", "QB A1", 87.0, 36.0)
    r2021 = rows[2021]
    assert (r2021.name, r2021.finish, r2021.in_progress, r2021.seed) == ("Alpha Prime", "In progress", True, None)


@pytest.mark.parametrize(
    "franchise_id, finish",
    [("0003", "Runner-up"), ("0002", "Lost Semifinal"), ("0004", "Lost Semifinal")],
)
def test_other_finishes(franchise_id, finish):
    rows = {row.year: row for row in franchises.season_rows(league(), franchise_id)}
    assert rows[2020].finish == finish


def test_missed_playoffs_when_never_seeded():
    s = build_season(
        2020,
        PLAYERS,
        {1: [(lineup("0001", {"a1": 20.0}), lineup("0002", {"a2": 10.0}))], 2: [(lineup("0001", {"a1": 1.0}), lineup("0002", {"a2": 2.0}))]},
        last_regular_season_week=1,
        franchises=("0001", "0002"),
        bracket=(BracketGame(2, "1", 0, "0001", "0002", 1, 2),),
    )
    rows = franchises.season_rows(League.build([s]), "0001")
    assert rows[0].finish == "Runner-up"
    s_no_bracket = build_season(2020, PLAYERS, {1: [(lineup("0001", {"a1": 20.0}), lineup("0002", {"a2": 10.0}))]}, 1, franchises=("0001", "0002"))
    assert franchises.season_rows(League.build([s_no_bracket]), "0001")[0].finish == "Missed playoffs"


def test_history_totals_eras_and_streaks():
    history = franchises.franchise_history(league(), "0001")
    assert history.name == "Alpha Prime"
    assert [e.era for e in history.eras] == [Era("0001", "Alpha Prime", 2021, 2021), Era("0001", "Alpha", 2020, 2020)]
    assert [row.year for row in history.eras[1].rows] == [2020]
    totals = history.totals
    assert (totals.games, totals.wins, totals.losses, totals.ties) == (3, 2, 1, 0)
    assert (totals.points_for, totals.points_against) == (42.0, 33.0)
    assert (totals.playoff_apps, totals.playoff_wins, totals.playoff_losses, totals.titles) == (1, 2, 0, 1)
    assert totals.record == "2-1-0"
    assert round(totals.win_pct, 3) == 0.667
    assert history.eras[1].totals.titles == 1 and history.eras[0].totals.titles == 0
    assert history.streak == "W3"
    assert (history.longest_win_streak, history.longest_loss_streak) == (3, 1)
    assert history.best_season.year == 2020 and history.worst_season.year == 2020
    assert [g.year for g in history.playoff_games] == [2020, 2020]
    assert history.playoff_games[0].round_name == "Final"


def test_head_to_head_series():
    history = franchises.franchise_history(league(), "0001")
    by_opponent = {s.opponent_id: s for s in history.series}
    beta = by_opponent["0002"]
    assert (beta.opponent_name, beta.wins, beta.losses, beta.ties) == ("Beta", 2, 0, 0)
    assert (beta.regular, beta.playoff) == ((2, 0, 0), (0, 0, 0))
    assert (beta.points_for, beta.points_against, beta.avg_margin, beta.streak) == (30.0, 15.0, 7.5, "W2")
    assert beta.last.year == 2021 and beta.last.result == "W"
    gamma = by_opponent["0003"]
    assert (gamma.wins, gamma.losses, gamma.regular, gamma.playoff) == (1, 1, (0, 1, 0), (1, 0, 0))
    assert gamma.avg_margin == 2.0 and gamma.streak == "W1"
    assert [m.week for m in gamma.meetings] == [2, 4]
    assert gamma.meetings[1].round_name == "Final"
    assert gamma.meetings[0].own_name == "Alpha"
    assert [s.opponent_name for s in history.series] == ["Beta", "Delta", "Gamma"]


def test_top_starters_for_a_franchise():
    history = franchises.franchise_history(league(), "0001")
    assert [t.player_id for t in history.top_starters] == ["a1"]
    a1 = history.top_starters[0]
    # Career vor is the 2020 total (36.0, see above) plus 2021 Week 1: a1 scores 10.0 against
    # a2's 5.0, a pool of two whose baseline is the worse score -- a2's own 5.0 -- so a1's vor
    # that week is 10.0 - 5.0 = 5.0. Career total is 36.0 + 5.0 = 41.0.
    assert (a1.name, a1.position, a1.first_year, a1.last_year, a1.starts, a1.points, a1.vor) == ("QB A1", "QB", 2020, 2021, 5, 97.0, 41.0)


def test_all_franchises_covers_every_id():
    assert sorted(franchises.all_franchises(league())) == ["0001", "0002", "0003", "0004"]


def test_season_rows_and_totals_carry_all_play_and_luck():
    rows = {row.year: row for row in franchises.season_rows(league(), "0001")}
    assert (rows[2020].allplay, rows[2020].expected_wins, rows[2020].luck) == ((5, 1, 0), 1.67, -0.7)
    assert (rows[2021].allplay, rows[2021].expected_wins, rows[2021].luck) == ((1, 0, 0), 1.0, 0.0)
    history = franchises.franchise_history(league(), "0001")
    totals = history.totals
    assert (totals.allplay_wins, totals.allplay_losses, totals.allplay_ties) == (6, 1, 0)
    assert totals.allplay_record == "6-1-0"
    assert round(totals.allplay_pct, 3) == 0.857
    assert totals.expected_wins == 2.67
    assert totals.luck == -0.7  # 2 actual wins minus 2.67 expected
    assert history.eras[1].totals.luck == -0.7 and history.eras[0].totals.luck == 0.0
    delta = franchises.franchise_history(league(), "0004").totals
    assert (delta.allplay_record, delta.luck) == ("1-5-0", 0.7)
