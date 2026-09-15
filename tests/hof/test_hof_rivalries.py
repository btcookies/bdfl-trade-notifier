from synthetic import four_team_league

from hof.stats import franchises, rivalries


def grid(min_meetings=rivalries.MIN_MEETINGS):
    return rivalries.rivalry_grid(franchises.all_franchises(four_team_league()), min_meetings=min_meetings)


def test_order_matches_the_franchises_index():
    assert grid().order == ("0003", "0001", "0004", "0002")


def test_cells_are_from_the_row_franchise_point_of_view():
    cells = grid().cells
    assert cells[("0001", "0002")] == (2, 0, 0)
    assert cells[("0002", "0001")] == (0, 2, 0)
    assert cells[("0001", "0003")] == (1, 1, 0)
    assert ("0001", "0001") not in cells
    assert len(cells) == 12  # every ordered pair has met at least once


def test_pair_lists_respect_the_minimum_meetings():
    everything = grid()
    assert [(p.a_name, p.b_name, p.meetings) for p in everything.most_played] == [
        ("Alpha Prime", "Beta", 2), ("Alpha Prime", "Gamma", 2), ("Alpha Prime", "Delta", 1), ("Beta", "Delta", 1), ("Beta", "Gamma", 1),
    ]
    assert everything.most_lopsided == () and everything.most_even == ()  # nobody has met five times
    loose = grid(min_meetings=1)
    # every pair but Alpha Prime–Gamma is one-sided (gap .5): the two-meeting pair first, then by name
    assert [(p.a_name, p.b_name) for p in loose.most_lopsided] == [
        ("Alpha Prime", "Beta"), ("Alpha Prime", "Delta"), ("Beta", "Delta"), ("Beta", "Gamma"), ("Gamma", "Delta"),
    ]
    assert (loose.most_even[0].a_name, loose.most_even[0].b_name, loose.most_even[0].gap) == ("Alpha Prime", "Gamma", 0.0)


def test_pair_leader_line():
    loose = grid(min_meetings=1)
    by_names = {(p.a_name, p.b_name): p for p in loose.most_played}
    assert by_names[("Alpha Prime", "Beta")].leader_line == "Alpha Prime leads Beta 2-0"
    assert by_names[("Beta", "Delta")].leader_line == "Delta leads Beta 1-0"
    assert by_names[("Alpha Prime", "Gamma")].leader_line == "Alpha Prime and Gamma are even at 1-1"
    tie = rivalries.Pair("0001", "A", "0002", "B", 3, 1, 1)
    assert (tie.meetings, tie.record, tie.leader_line, round(tie.gap, 3)) == (5, "3-1-1", "A leads B 3-1-1", 0.2)
