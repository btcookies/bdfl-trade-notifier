# Analytics Layer, Plan 1 of 3: Stats and Records

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute all-play records and luck, formula power rankings, nine weekly awards with a season tally, an all-time rivalry grid, and three new records-book tables, and attach them to the existing `Model` so Plans 2 (site and mobile) and 3 (Discord) can render them.

**Architecture:** Five new modules under `hof/stats/` (`allplay`, `power`, `awards`, `analytics`, `rivalries`) that read the already-loaded `League`/`Season` model and return frozen dataclasses. `franchises.SeasonRow`/`Totals` gain all-play and luck fields, `records.TABLES` gains three season tables, `Config` gains optional award labels, and `stats.model.compute()` bundles everything. No fetch, template, or Discord changes in this plan.

**Tech Stack:** Python 3.13, dataclasses, pytest (no network), ruff. Run everything from the repo root with the project venv active (`source .venv/bin/activate`; from a worktree, `../../../.venv/bin/python -m pytest` works too).

**Spec:** `docs/superpowers/specs/2026-09-08-analytics-layer-design.md`, sections 3 and the records/config parts of 4. Read it first.

**Conventions you must follow:**
- Tests live in `tests/hof/`, import the synthetic league with `from synthetic import four_team_league, build_season, lineup`, and never touch the network.
- Franchise ids (`"0001"`) never appear in rendered text; these modules only return ids and names, so that rule is Plan 2's concern, but keep ids and names separate fields as the existing code does.
- Every number that is displayed is rounded where it is computed (one decimal for points and luck, two for expected wins, three for percentages and power scores), so output is deterministic.
- Line length 100 (ruff ignores E501 but keep lines readable). Run `ruff check hof tests` before every commit.

**The synthetic league, which every hand-computed value below relies on** (`tests/hof/synthetic.py`, `four_team_league()`):

2020, regular season weeks 1–2, playoffs weeks 3–4, names Alpha (0001), Beta (0002), Gamma (0003), Delta (0004):

| Week | Games (home score – away score) | Notes |
|---|---|---|
| 1 | Alpha 20.0 – Beta 10.0; Gamma 15.0 – Delta 5.0 | Beta's optimal was 14.0 (4.0 left on the bench); everyone else optimal |
| 2 | Alpha 12.0 – Gamma 18.0; Beta 9.0 – Delta 11.0 | |
| 3 (Semifinal) | Gamma 20.0 – Beta 10.0; Alpha 25.0 – Delta 5.0 | playoff |
| 4 (Final) | Gamma 20.0 – Alpha 30.0 | playoff; Alpha is champion |

2021 (in progress, Alpha renamed Alpha Prime): week 1 Alpha Prime 10.0 – Beta 5.0 only.

All-play, 2020 (regular season only): week 1 scores 20/15/10/5 give Alpha 3-0-0, Gamma 2-1-0, Beta 1-2-0, Delta 0-3-0; week 2 scores 18/12/11/9 give Gamma 3-0-0, Alpha 2-1-0, Delta 1-2-0, Beta 0-3-0. Season: Alpha 5-1-0 (expected wins 1.67, actual 1, luck −0.7), Gamma 5-1-0 (1.67, actual 2, luck +0.3), Beta 1-5-0 (0.33, actual 0, luck −0.3), Delta 1-5-0 (0.33, actual 1, luck +0.7).

---

### Task 1: All-play records and luck

**Files:**
- Create: `hof/stats/allplay.py`
- Test: `tests/hof/test_hof_allplay.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/hof/test_hof_allplay.py
from synthetic import build_season, four_team_league, lineup

from hof.stats import allplay
from hof.stats.league import League

PLAYERS = {f"a{i}": (f"QB A{i}", "QB") for i in range(1, 5)}


def test_all_play_week_compares_every_counted_score():
    season = four_team_league().season(2020)
    rows = {row.franchise_id: row for row in allplay.all_play_week(season, 1)}
    assert (rows["0001"].wins, rows["0001"].losses, rows["0001"].ties) == (3, 0, 0)
    assert (rows["0003"].wins, rows["0003"].losses, rows["0003"].ties) == (2, 1, 0)
    assert (rows["0002"].wins, rows["0002"].losses, rows["0002"].ties) == (1, 2, 0)
    assert (rows["0004"].wins, rows["0004"].losses, rows["0004"].ties) == (0, 3, 0)
    assert rows["0001"].expected_wins == 1.0
    assert round(rows["0003"].expected_wins, 4) == 0.6667
    assert rows["0003"].record == "2-1-0"


def test_playoff_weeks_and_empty_weeks_produce_no_rows():
    season = four_team_league().season(2020)
    assert [row.week for row in allplay.all_play_weeks(season)] == [1, 1, 1, 1, 2, 2, 2, 2]
    assert allplay.all_play_week(season, 3) == []  # playoff week
    assert allplay.all_play_week(season, 9) == []  # no such week
    assert allplay.regular_weeks(season) == [1, 2]
    assert allplay.regular_weeks(season, through_week=1) == [1]


def test_ties_count_half():
    season = build_season(
        2020, PLAYERS,
        {1: [(lineup("0001", {"a1": 10.0}), lineup("0002", {"a2": 10.0}))]},
        last_regular_season_week=1, franchises=("0001", "0002"),
    )
    rows = allplay.all_play_week(season, 1)
    assert [(r.wins, r.losses, r.ties, r.expected_wins) for r in rows] == [(0, 0, 1, 0.5), (0, 0, 1, 0.5)]
    line = {s.franchise_id: s for s in allplay.standings(League.build([season]), season)}["0001"]
    assert (line.wins, line.losses, line.ties, line.allplay, line.expected_wins, line.luck) == (0, 0, 1, (0, 0, 1), 0.5, 0.0)


def test_season_standings_with_all_play_and_luck():
    league = four_team_league()
    lines = allplay.standings(league, league.season(2020))
    assert [line.name for line in lines] == ["Gamma", "Alpha", "Delta", "Beta"]
    by_id = {line.franchise_id: line for line in lines}
    alpha = by_id["0001"]
    assert (alpha.wins, alpha.losses, alpha.ties, alpha.points_for, alpha.points_against) == (1, 1, 0, 32.0, 28.0)
    assert (alpha.allplay, alpha.expected_wins, alpha.luck) == ((5, 1, 0), 1.67, -0.7)
    assert (alpha.record, alpha.allplay_record, round(alpha.allplay_pct, 3), alpha.games) == ("1-1-0", "5-1-0", 0.833, 2)
    assert (by_id["0003"].allplay, by_id["0003"].expected_wins, by_id["0003"].luck) == ((5, 1, 0), 1.67, 0.3)
    assert (by_id["0002"].allplay, by_id["0002"].expected_wins, by_id["0002"].luck) == ((1, 5, 0), 0.33, -0.3)
    assert (by_id["0004"].allplay, by_id["0004"].expected_wins, by_id["0004"].luck) == ((1, 5, 0), 0.33, 0.7)


def test_standings_through_an_earlier_week():
    league = four_team_league()
    lines = {s.franchise_id: s for s in allplay.standings(league, league.season(2020), through_week=1)}
    assert (lines["0001"].wins, lines["0001"].allplay, lines["0001"].expected_wins, lines["0001"].luck) == (1, (3, 0, 0), 1.0, 0.0)
    assert (lines["0003"].allplay, lines["0003"].luck) == ((2, 1, 0), 0.3)
    assert lines["0004"].points_for == 5.0


def test_franchises_without_a_game_still_get_a_line():
    league = four_team_league()
    lines = allplay.standings(league, league.season(2021))
    assert [line.name for line in lines] == ["Alpha Prime", "Beta", "Delta", "Gamma"]
    gamma = lines[3]
    assert (gamma.games, gamma.allplay, gamma.expected_wins, gamma.luck) == (0, (0, 0, 0), 0.0, 0.0)
    assert (lines[0].allplay, lines[0].expected_wins, lines[0].luck) == ((1, 0, 0), 1.0, 0.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/hof/test_hof_allplay.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hof.stats.allplay'`

- [ ] **Step 3: Write the module**

```python
# hof/stats/allplay.py
"""All-play records and luck: every franchise against every other counted score, week by week.

A week's all-play record is out of (franchises with a counted score that week) - 1. Expected
wins for a week is the all-play win share; season expected wins is the sum over weeks played;
luck is actual wins (ties count half) minus expected wins. Playoff weeks are excluded because
not every franchise plays a counted game.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from hof.model.season import Season
from hof.stats.league import League


@dataclass(frozen=True)
class AllPlayWeek:
    """One franchise's week measured against every other counted score that week."""

    franchise_id: str
    week: int
    wins: int
    losses: int
    ties: int

    @property
    def expected_wins(self) -> float:
        compared = self.wins + self.losses + self.ties
        return (self.wins + 0.5 * self.ties) / compared if compared else 0.0

    @property
    def record(self) -> str:
        return f"{self.wins}-{self.losses}-{self.ties}"


@dataclass(frozen=True)
class StandingLine:
    """A franchise's regular-season line through a week, with its all-play record and luck."""

    franchise_id: str
    name: str  # the name used that season
    wins: int
    losses: int
    ties: int
    points_for: float
    points_against: float
    allplay: tuple[int, int, int]
    expected_wins: float  # two decimals
    luck: float  # one decimal, signed

    @property
    def games(self) -> int:
        return self.wins + self.losses + self.ties

    @property
    def record(self) -> str:
        return f"{self.wins}-{self.losses}-{self.ties}"

    @property
    def allplay_record(self) -> str:
        return "-".join(str(n) for n in self.allplay)

    @property
    def allplay_pct(self) -> float:
        wins, losses, ties = self.allplay
        total = wins + losses + ties
        return (wins + 0.5 * ties) / total if total else 0.0


def scores_by_week(season: Season) -> dict[int, dict[str, float]]:
    """week -> franchise id -> counted regular-season score, from one pass over the games."""
    out: dict[int, dict[str, float]] = {}
    for game in season.games():
        if game.playoff:
            continue
        week = out.setdefault(game.week, {})
        for lineup in (game.home, game.away):
            week[lineup.franchise_id] = lineup.score or 0.0
    return out


def regular_weeks(season: Season, through_week: int | None = None) -> list[int]:
    """Regular-season weeks with at least one counted game, ascending, up to through_week."""
    weeks = sorted(scores_by_week(season))
    if through_week is not None:
        weeks = [w for w in weeks if w <= through_week]
    return weeks


def _rows(week: int, scores: dict[str, float]) -> list[AllPlayWeek]:
    """One row per franchise with a counted score, by id; none when fewer than two scored."""
    if len(scores) < 2:
        return []
    rows: list[AllPlayWeek] = []
    for fid, score in sorted(scores.items()):
        others = [s for other, s in scores.items() if other != fid]
        rows.append(
            AllPlayWeek(
                franchise_id=fid,
                week=week,
                wins=sum(1 for s in others if score > s),
                losses=sum(1 for s in others if score < s),
                ties=sum(1 for s in others if score == s),
            )
        )
    return rows


def all_play_week(season: Season, week: int) -> list[AllPlayWeek]:
    return _rows(week, scores_by_week(season).get(week, {}))


def all_play_weeks(season: Season, through_week: int | None = None) -> list[AllPlayWeek]:
    by_week = scores_by_week(season)
    return [
        row
        for week in sorted(by_week)
        if through_week is None or week <= through_week
        for row in _rows(week, by_week[week])
    ]


def _order(season: Season, through_week: int | None) -> Callable[[StandingLine], tuple]:
    """MFL's standings order when the export is present and the lines are current; else by
    win percentage, points for, and name."""
    newest = regular_weeks(season)
    current = through_week is None or (bool(newest) and through_week >= newest[-1])
    if season.standings and current:
        position = {s.franchise_id: i for i, s in enumerate(season.standings)}
        return lambda line: (position.get(line.franchise_id, len(position)), line.name)
    return lambda line: (-(line.wins + 0.5 * line.ties), -line.points_for, line.name)


def standings(league: League, season: Season, through_week: int | None = None) -> list[StandingLine]:
    """Every franchise's regular-season line through the week (every week when None)."""
    weeks = set(regular_weeks(season, through_week))
    ids = list(season.franchises)
    wins = dict.fromkeys(ids, 0)
    losses = dict.fromkeys(ids, 0)
    ties = dict.fromkeys(ids, 0)
    points_for = dict.fromkeys(ids, 0.0)
    points_against = dict.fromkeys(ids, 0.0)
    for game in season.games():
        if game.playoff or game.week not in weeks:
            continue
        for own, other in ((game.home, game.away), (game.away, game.home)):
            fid = own.franchise_id
            own_score, other_score = own.score or 0.0, other.score or 0.0
            points_for[fid] = points_for.get(fid, 0.0) + own_score
            points_against[fid] = points_against.get(fid, 0.0) + other_score
            if own_score > other_score:
                wins[fid] = wins.get(fid, 0) + 1
            elif own_score < other_score:
                losses[fid] = losses.get(fid, 0) + 1
            else:
                ties[fid] = ties.get(fid, 0) + 1
    allplay: dict[str, list[int]] = {fid: [0, 0, 0] for fid in ids}
    expected = dict.fromkeys(ids, 0.0)
    for row in all_play_weeks(season, through_week):
        record = allplay.setdefault(row.franchise_id, [0, 0, 0])
        record[0] += row.wins
        record[1] += row.losses
        record[2] += row.ties
        expected[row.franchise_id] = expected.get(row.franchise_id, 0.0) + row.expected_wins
    lines = [
        StandingLine(
            franchise_id=fid,
            name=league.name_in(fid, season.year),
            wins=wins.get(fid, 0),
            losses=losses.get(fid, 0),
            ties=ties.get(fid, 0),
            points_for=round(points_for.get(fid, 0.0), 1),
            points_against=round(points_against.get(fid, 0.0), 1),
            allplay=(allplay[fid][0], allplay[fid][1], allplay[fid][2]),
            expected_wins=round(expected.get(fid, 0.0), 2),
            luck=round(wins.get(fid, 0) + 0.5 * ties.get(fid, 0) - expected.get(fid, 0.0), 1),
        )
        for fid in set(ids) | set(allplay)
    ]
    return sorted(lines, key=_order(season, through_week))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/hof/test_hof_allplay.py -v`
Expected: 6 passed

- [ ] **Step 5: Lint and commit**

```bash
ruff check hof tests && git add hof/stats/allplay.py tests/hof/test_hof_allplay.py && git commit -m "hof: all-play records, expected wins, and luck"
```

---

### Task 2: All-play and luck on franchise season rows and totals

**Files:**
- Modify: `hof/stats/franchises.py` (the `Totals` and `SeasonRow` dataclasses, `season_row()`, `totals()`)
- Test: `tests/hof/test_hof_franchises.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/hof/test_hof_franchises.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/hof/test_hof_franchises.py::test_season_rows_and_totals_carry_all_play_and_luck -v`
Expected: FAIL with `AttributeError: 'SeasonRow' object has no attribute 'allplay'`

- [ ] **Step 3: Extend the dataclasses and the builders**

In `hof/stats/franchises.py`, add the import and the fields. The new fields have defaults so existing constructors keep working.

```python
from hof.stats import allplay
```
(add after `from hof.model.season import Lineup, Season`; ruff's isort wants `from hof.stats import allplay` before `from hof.stats.league import Era, League`)

Replace the `Totals` class with:

```python
@dataclass(frozen=True)
class Totals:
    games: int
    wins: int
    losses: int
    ties: int
    points_for: float
    points_against: float
    playoff_apps: int
    playoff_wins: int
    playoff_losses: int
    titles: int
    allplay_wins: int = 0
    allplay_losses: int = 0
    allplay_ties: int = 0
    expected_wins: float = 0.0  # two decimals

    @property
    def win_pct(self) -> float:
        return (self.wins + 0.5 * self.ties) / self.games if self.games else 0.0

    @property
    def record(self) -> str:
        return f"{self.wins}-{self.losses}-{self.ties}"

    @property
    def allplay_record(self) -> str:
        return f"{self.allplay_wins}-{self.allplay_losses}-{self.allplay_ties}"

    @property
    def allplay_pct(self) -> float:
        total = self.allplay_wins + self.allplay_losses + self.allplay_ties
        return (self.allplay_wins + 0.5 * self.allplay_ties) / total if total else 0.0

    @property
    def luck(self) -> float:
        return round(self.wins + 0.5 * self.ties - self.expected_wins, 1)
```

Add three fields at the end of `SeasonRow` (after `top_starter`):

```python
    allplay: tuple[int, int, int] = (0, 0, 0)
    expected_wins: float = 0.0
    luck: float = 0.0
```

In `season_row()`, compute the line once and pass the fields. Add this line right after `standing = next(...)`:

```python
    line = next((s for s in allplay.standings(league, season, None) if s.franchise_id == franchise_id), None)
```

and add to the `SeasonRow(...)` call, after `top_starter=...`:

```python
        allplay=line.allplay if line else (0, 0, 0),
        expected_wins=line.expected_wins if line else 0.0,
        luck=line.luck if line else 0.0,
```

In `totals()`, add to the `Totals(...)` call after `titles=...`:

```python
        allplay_wins=sum(r.allplay[0] for r in rows),
        allplay_losses=sum(r.allplay[1] for r in rows),
        allplay_ties=sum(r.allplay[2] for r in rows),
        expected_wins=round(sum(r.expected_wins for r in rows), 2),
```

- [ ] **Step 4: Run the franchise tests to verify they pass**

Run: `pytest tests/hof/test_hof_franchises.py -v`
Expected: all passed (the new test and every existing one)

- [ ] **Step 5: Lint and commit**

```bash
ruff check hof tests && git add hof/stats/franchises.py tests/hof/test_hof_franchises.py && git commit -m "hof: all-play and luck on franchise season rows and totals"
```

---

### Task 3: Power rankings

**Files:**
- Create: `hof/stats/power.py`
- Test: `tests/hof/test_hof_power.py`

Hand-computed 2020 values (score = 0.5 × all-play % + 0.3 × win % + 0.2 × form, rounded to three decimals):

| Through week | Franchise | All-play % | Win % | Form | Score | Rank (prev) |
|---|---|---|---|---|---|---|
| 1 | Alpha | 1.000 | 1.000 | 1.000 | 1.000 | 1 (new) |
| 1 | Gamma | .667 | 1.000 | .667 | 0.767 | 2 (new) |
| 1 | Beta | .333 | 0 | .333 | 0.233 | 3 (new) |
| 1 | Delta | 0 | 0 | 0 | 0.000 | 4 (new) |
| 2 | Gamma | .833 | 1.000 | .833 | 0.883 | 1 (2, ▲1) |
| 2 | Alpha | .833 | .500 | .833 | 0.733 | 2 (1, ▼1) |
| 2 | Delta | .167 | .500 | .167 | 0.267 | 3 (4, ▲1) |
| 2 | Beta | .167 | 0 | .167 | 0.117 | 4 (3, ▼1) |

- [ ] **Step 1: Write the failing tests**

```python
# tests/hof/test_hof_power.py
from synthetic import build_season, four_team_league, lineup

from hof.stats import power
from hof.stats.league import League

PLAYERS = {f"a{i}": (f"QB A{i}", "QB") for i in range(1, 5)}


def test_first_ranked_week_has_no_previous_rank():
    league = four_team_league()
    lines = power.rankings(league, league.season(2020), through_week=1)
    assert [(l.rank, l.name, l.score, l.previous_rank, l.movement) for l in lines] == [
        (1, "Alpha", 1.0, None, None),
        (2, "Gamma", 0.767, None, None),
        (3, "Beta", 0.233, None, None),
        (4, "Delta", 0.0, None, None),
    ]
    gamma = lines[1]
    assert (gamma.allplay_pct, gamma.win_pct, gamma.form) == (0.667, 1.0, 0.667)


def test_second_week_ranks_and_movement():
    league = four_team_league()
    lines = power.rankings(league, league.season(2020), through_week=2)
    assert [(l.rank, l.name, l.score, l.previous_rank, l.movement) for l in lines] == [
        (1, "Gamma", 0.883, 2, 1),
        (2, "Alpha", 0.733, 1, -1),
        (3, "Delta", 0.267, 4, 1),
        (4, "Beta", 0.117, 3, -1),
    ]


def test_playoff_weeks_keep_the_final_regular_season_ranking():
    league = four_team_league()
    season = league.season(2020)
    assert power.rankings(league, season, through_week=4) == power.rankings(league, season, through_week=2)
    assert power.rankings(league, season, through_week=None) == power.rankings(league, season, through_week=2)
    assert power.ranked_weeks(season) == [1, 2]


def test_form_pools_the_last_three_weeks():
    weeks = {
        1: [(lineup("0001", {"a1": 20.0}), lineup("0002", {"a2": 10.0}))],
        2: [(lineup("0001", {"a1": 20.0}), lineup("0002", {"a2": 10.0}))],
        3: [(lineup("0001", {"a1": 20.0}), lineup("0002", {"a2": 10.0}))],
        4: [(lineup("0001", {"a1": 10.0}), lineup("0002", {"a2": 20.0}))],
    }
    season = build_season(2020, PLAYERS, weeks, last_regular_season_week=4, franchises=("0001", "0002"))
    lines = power.rankings(League.build([season]), season, through_week=4)
    top = lines[0]
    assert top.franchise_id == "0001"
    assert (top.allplay_pct, top.win_pct, top.form) == (0.75, 0.75, 0.667)  # form: weeks 2-4, 2-1
    assert top.score == 0.733  # 0.375 + 0.225 + 0.133
    assert (lines[1].form, lines[1].score) == (0.333, 0.267)


def test_ties_break_on_points_for_then_name():
    weeks = {1: [(lineup("0001", {"a1": 20.0}), lineup("0002", {"a2": 20.0})), (lineup("0003", {"a3": 30.0}), lineup("0004", {"a4": 30.0}))]}
    season = build_season(2020, PLAYERS, weeks, last_regular_season_week=2)
    lines = power.rankings(League.build([season]), season, through_week=1)
    # Both games are ties, so every win % is .5. 0003 and 0004 scored 30 against two 20s, so
    # their all-play is 2-0-1 (.833) and 0001/0002 are 0-2-1 (.167). Score for 0003 and 0004:
    # 0.5 × .833 + 0.3 × .5 + 0.2 × .833 = 0.733; equal scores and equal points for (30.0), so
    # the name decides.
    assert [(l.name, l.score) for l in lines] == [("Team 0003", 0.733), ("Team 0004", 0.733), ("Team 0001", 0.267), ("Team 0002", 0.267)]
    assert [l.rank for l in lines] == [1, 2, 3, 4]


def test_franchises_without_a_game_are_not_ranked():
    league = four_team_league()
    lines = power.rankings(league, league.season(2021), through_week=1)
    assert [(l.rank, l.name, l.score) for l in lines] == [(1, "Alpha Prime", 1.0), (2, "Beta", 0.0)]


def test_no_ranking_before_the_first_game():
    season = build_season(2020, PLAYERS, {}, last_regular_season_week=2)
    assert power.rankings(League.build([season]), season, through_week=None) == []
```

Note on the tie-break test: with equal scores and equal points for (30.0 and 30.0), the order falls to the name, so "Team 0003" precedes "Team 0004".

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/hof/test_hof_power.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hof.stats.power'`

- [ ] **Step 3: Write the module**

```python
# hof/stats/power.py
"""Power rankings: a transparent composite of all-play strength, actual record, and recent form.

    score = 0.5 * all-play % (season to date)
          + 0.3 * win % (ties count half)
          + 0.2 * form, the all-play % over the last three regular-season weeks pooled

Computed after each regular-season week with a counted game. The last regular-season ranking
stands through the playoffs. Ties break on points for, then name.
"""

from __future__ import annotations

from dataclasses import dataclass

from hof.model.season import Season
from hof.stats import allplay
from hof.stats.league import League

WEIGHT_ALLPLAY = 0.5
WEIGHT_RECORD = 0.3
WEIGHT_FORM = 0.2
FORM_WEEKS = 3
FORMULA = (
    "Score = 0.5 × all-play % + 0.3 × win % + 0.2 × form, "
    "where form is all-play % over the last three weeks."
)


@dataclass(frozen=True)
class PowerLine:
    rank: int
    franchise_id: str
    name: str  # the name used that season
    score: float  # three decimals
    allplay_pct: float  # three decimals
    win_pct: float  # three decimals
    form: float  # three decimals
    previous_rank: int | None

    @property
    def movement(self) -> int | None:
        """Places gained (positive) or lost since the previous ranked week; None the first week."""
        return None if self.previous_rank is None else self.previous_rank - self.rank


def ranked_weeks(season: Season) -> list[int]:
    """Regular-season weeks that get a ranking: those with a counted game."""
    return allplay.regular_weeks(season)


def _pct(wins: int, losses: int, ties: int) -> float:
    total = wins + losses + ties
    return (wins + 0.5 * ties) / total if total else 0.0


def _table(league: League, season: Season, through_week: int) -> list[tuple[str, float, float, float, float]]:
    """(franchise id, score, all-play %, win %, form) for every franchise with a counted game
    through the week, best first."""
    weeks = allplay.regular_weeks(season, through_week)
    recent = set(weeks[-FORM_WEEKS:])
    recent_allplay: dict[str, list[int]] = {}
    for row in allplay.all_play_weeks(season, through_week):
        if row.week in recent:
            record = recent_allplay.setdefault(row.franchise_id, [0, 0, 0])
            record[0] += row.wins
            record[1] += row.losses
            record[2] += row.ties
    rows = []
    for line in allplay.standings(league, season, through_week):
        if not line.games:
            continue
        form = _pct(*recent_allplay.get(line.franchise_id, [0, 0, 0]))
        win_pct = _pct(line.wins, line.losses, line.ties)
        score = round(WEIGHT_ALLPLAY * line.allplay_pct + WEIGHT_RECORD * win_pct + WEIGHT_FORM * form, 3)
        rows.append((line.franchise_id, score, line.allplay_pct, win_pct, form, line.points_for, line.name))
    rows.sort(key=lambda r: (-r[1], -r[5], r[6]))
    return [(fid, score, ap, wp, form) for fid, score, ap, wp, form, _, _ in rows]


def rankings(league: League, season: Season, through_week: int | None = None) -> list[PowerLine]:
    """The ranking as of the newest ranked week at or before through_week (every week when None)."""
    weeks = allplay.regular_weeks(season, through_week)
    if not weeks:
        return []
    current = _table(league, season, weeks[-1])
    previous: dict[str, int] = {}
    if len(weeks) > 1:
        previous = {fid: i + 1 for i, (fid, *_) in enumerate(_table(league, season, weeks[-2]))}
    return [
        PowerLine(
            rank=i + 1,
            franchise_id=fid,
            name=league.name_in(fid, season.year),
            score=score,
            allplay_pct=round(ap, 3),
            win_pct=round(wp, 3),
            form=round(form, 3),
            previous_rank=previous.get(fid),
        )
        for i, (fid, score, ap, wp, form) in enumerate(current)
    ]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/hof/test_hof_power.py -v`
Expected: 7 passed. If `test_ties_break_on_points_for_then_name` fails on the expected scores, recompute by hand before touching the module: 0003's all-play through week 1 is 2-0-1 (beat both 20s, tied 0004) → .833; win % .5 (a tie); form .833; score = .4167 + .15 + .1667 = .733.

- [ ] **Step 5: Lint and commit**

```bash
ruff check hof tests && git add hof/stats/power.py tests/hof/test_hof_power.py && git commit -m "hof: formula power rankings with movement"
```

---

### Task 4: Weekly awards, labels, tally, and leaders

**Files:**
- Create: `hof/stats/awards.py`
- Test: `tests/hof/test_hof_awards.py`

Hand-computed awards for the synthetic 2020 (holder, value):

| Week | high_score | low_score | blowout | closest | best_lineup | worst_lineup | lucky_win | unlucky_loss |
|---|---|---|---|---|---|---|---|---|
| 1 | Alpha 20.0 | Delta 5.0 | Alpha 10.0 (tie with Gamma's 10.0, Alpha scored more) | Alpha 10.0 (same tie) | Alpha 100% (three at 100%, Alpha scored most) | Beta 4.0 | Gamma 15.0, all-play 2-1-0 | Beta 10.0, all-play 1-2-0 |
| 2 | Gamma 18.0 | Beta 9.0 | Gamma 6.0 | Delta 2.0 | Gamma 100% | Gamma 0.0 | Delta 11.0, 1-2-0 | Alpha 12.0, 2-1-0 |
| 3 (playoff) | Alpha 25.0 | Delta 5.0 | Alpha 20.0 | Gamma 10.0 | Alpha 100% | Alpha 0.0 | Gamma 20.0 (no all-play detail) | Beta 10.0 (no detail) |
| 4 (playoff) | Alpha 30.0 | Gamma 20.0 | Alpha 10.0 | Alpha 10.0 | Alpha 100% | Alpha 0.0 | Alpha 30.0 | Gamma 20.0 |

No lineup has a bench player, so `best_benched` is absent every week. Season tally: Alpha 15, Gamma 9, Beta 4, Delta 4 (32 awards = 8 per week × 4 weeks).

- [ ] **Step 1: Write the failing tests**

```python
# tests/hof/test_hof_awards.py
from synthetic import build_season, four_team_league, lineup

from hof.stats import awards
from hof.stats.awards import AWARD_KEYS, DEFAULT_LABELS, Award
from hof.stats.league import League

PLAYERS = {f"a{i}": (f"QB A{i}", "QB") for i in range(1, 5)}


def by_key(items):
    return {award.key: award for award in items}


def test_award_keys_and_default_labels_line_up():
    assert AWARD_KEYS == ("high_score", "low_score", "blowout", "closest", "best_lineup", "worst_lineup", "lucky_win", "unlucky_loss", "best_benched")
    assert tuple(DEFAULT_LABELS) == AWARD_KEYS
    assert awards.labels_with(None) == DEFAULT_LABELS
    assert awards.labels_with({"low_score": "Golden Goose Egg"})["low_score"] == "Golden Goose Egg"
    assert awards.labels_with({"low_score": "Golden Goose Egg"})["high_score"] == "Highest score"


def test_week_one_awards():
    league = four_team_league()
    week = awards.week_awards(league, league.season(2020), 1)
    assert [a.key for a in week] == list(AWARD_KEYS[:-1])  # no bench players, so no best_benched
    got = by_key(week)
    assert got["high_score"] == Award("high_score", "Highest score", "0001", "Alpha", "0001", 20.0, "pts", "beat Beta 20.0–10.0")
    assert got["low_score"] == Award("low_score", "Lowest score", "0004", "Delta", "0004", 5.0, "pts", "lost to Gamma 5.0–15.0")
    assert got["blowout"] == Award("blowout", "Biggest blowout", "0001", "Alpha", "0001", 10.0, "pts", "over Beta, 20.0–10.0")
    assert got["closest"] == Award("closest", "Closest game", "0001", "Alpha", "0001", 10.0, "pts", "over Beta, 20.0–10.0")
    assert got["best_lineup"] == Award("best_lineup", "Best lineup", "0001", "Alpha", "0001", 1.0, "pct", "20.0 of 20.0 possible")
    assert got["worst_lineup"] == Award("worst_lineup", "Most points left on the bench", "0002", "Beta", "0002", 4.0, "pts", "10.0 of 14.0 possible")
    assert got["lucky_win"] == Award("lucky_win", "Luckiest win", "0003", "Gamma", "0003", 15.0, "pts", "would have gone 2-1-0 against the field")
    assert got["unlucky_loss"] == Award("unlucky_loss", "Unluckiest loss", "0002", "Beta", "0002", 10.0, "pts", "would have gone 1-2-0 against the field")


def test_week_two_awards_and_label_overrides():
    league = four_team_league()
    got = by_key(awards.week_awards(league, league.season(2020), 2, {"lucky_win": "Horseshoe"}))
    assert (got["high_score"].holder_name, got["high_score"].value) == ("Gamma", 18.0)
    assert (got["low_score"].holder_name, got["low_score"].value) == ("Beta", 9.0)
    assert (got["blowout"].holder_name, got["blowout"].value, got["blowout"].detail) == ("Gamma", 6.0, "over Alpha, 18.0–12.0")
    assert (got["closest"].holder_name, got["closest"].value) == ("Delta", 2.0)
    assert (got["best_lineup"].holder_name, got["worst_lineup"].holder_name, got["worst_lineup"].value) == ("Gamma", "Gamma", 0.0)
    assert (got["lucky_win"].label, got["lucky_win"].holder_name, got["lucky_win"].detail) == ("Horseshoe", "Delta", "would have gone 1-2-0 against the field")
    assert (got["unlucky_loss"].holder_name, got["unlucky_loss"].value) == ("Alpha", 12.0)


def test_playoff_week_awards_cover_bracket_games_without_all_play_detail():
    league = four_team_league()
    got = by_key(awards.week_awards(league, league.season(2020), 4))
    assert (got["high_score"].holder_name, got["low_score"].holder_name) == ("Alpha", "Gamma")
    assert got["lucky_win"] == Award("lucky_win", "Luckiest win", "0001", "Alpha", "0001", 30.0, "pts", "")
    assert got["unlucky_loss"] == Award("unlucky_loss", "Unluckiest loss", "0003", "Gamma", "0003", 20.0, "pts", "")
    assert awards.week_awards(league, league.season(2020), 9) == []


def test_tie_is_the_closest_game_and_gives_no_lucky_or_unlucky():
    season = build_season(
        2020, PLAYERS,
        {1: [(lineup("0001", {"a1": 10.0}), lineup("0002", {"a2": 10.0}))]},
        last_regular_season_week=1, franchises=("0001", "0002"),
    )
    got = by_key(awards.week_awards(League.build([season]), season, 1))
    assert got["closest"] == Award("closest", "Closest game", "0001", "Team 0001", "0001", 0.0, "pts", "tied with Team 0002, 10.0–10.0")
    assert got["blowout"].value == 0.0
    assert got["high_score"].detail == "tied Team 0002 10.0–10.0"
    assert "lucky_win" not in got and "unlucky_loss" not in got


def test_best_benched_player_and_lineup_efficiency():
    players = {**PLAYERS, "b1": ("RB B1", "RB"), "b2": ("RB B2", "RB")}
    season = build_season(
        2020, players,
        {1: [
            (lineup("0001", {"a1": 20.0}, bench={"b1": 25.0}, opt_pts=45.0), lineup("0002", {"a2": 10.0}, bench={"b2": 12.0}, opt_pts=22.0)),
        ]},
        last_regular_season_week=1, franchises=("0001", "0002"),
    )
    got = by_key(awards.week_awards(League.build([season]), season, 1))
    assert got["best_benched"] == Award("best_benched", "Best player on a bench", "b1", "RB B1", "0001", 25.0, "pts", "on Team 0001's bench")
    assert got["best_lineup"] == Award("best_lineup", "Best lineup", "0002", "Team 0002", "0002", 0.455, "pct", "10.0 of 22.0 possible")
    assert got["worst_lineup"] == Award("worst_lineup", "Most points left on the bench", "0001", "Team 0001", "0001", 25.0, "pts", "20.0 of 45.0 possible")


def test_no_lineup_awards_without_optimal_points():
    season = build_season(
        2020, PLAYERS,
        {1: [(lineup("0001", {"a1": 20.0}), lineup("0002", {"a2": 10.0}))]},
        last_regular_season_week=1, franchises=("0001", "0002"),
    )
    from dataclasses import replace

    week = season.weeks[1]
    lineups = {fid: replace(lu, opt_pts=None) for fid, lu in week.lineups.items()}
    season = replace(season, weeks={1: replace(week, lineups=lineups)})
    keys = [a.key for a in awards.week_awards(League.build([season]), season, 1)]
    assert "best_lineup" not in keys and "worst_lineup" not in keys and "high_score" in keys


def test_format_value():
    assert awards.format_value(20.0, "pts") == "20.0"
    assert awards.format_value(0.4545, "pct") == "45.5%"
    assert awards.format_value(0.7, "wins") == "+0.7"
    assert awards.format_value(-0.7, "wins") == "-0.7"


def test_tally_and_leaders_for_the_season():
    league = four_team_league()
    season = league.season(2020)
    weeks = [awards.week_awards(league, season, week) for week in (1, 2, 3, 4)]
    counts = awards.tally(weeks, season.franchises)
    assert {fid: sum(c.values()) for fid, c in counts.items()} == {"0001": 15, "0002": 4, "0003": 9, "0004": 4}
    assert counts["0001"]["high_score"] == 3 and counts["0002"]["worst_lineup"] == 1
    assert set(counts["0004"]) == set(AWARD_KEYS)
    assert awards.leaders(counts) == (("0001",), 15)
    assert awards.leaders({"0001": dict.fromkeys(AWARD_KEYS, 0)}) == ((), 0)
    tied = {"0001": {**dict.fromkeys(AWARD_KEYS, 0), "high_score": 2}, "0002": {**dict.fromkeys(AWARD_KEYS, 0), "low_score": 2}}
    assert awards.leaders(tied) == (("0001", "0002"), 2)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/hof/test_hof_awards.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hof.stats.awards'`

- [ ] **Step 3: Write the module**

```python
# hof/stats/awards.py
"""Weekly awards: nine superlatives over a week's counted games.

Ties break on the holder's score that week (higher first), then on the holder's name, so the
output is deterministic. An award with no candidate is omitted.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from hof.model.season import Game, Lineup, Season
from hof.stats import allplay
from hof.stats.league import League

AWARD_KEYS = (
    "high_score",
    "low_score",
    "blowout",
    "closest",
    "best_lineup",
    "worst_lineup",
    "lucky_win",
    "unlucky_loss",
    "best_benched",
)
DEFAULT_LABELS = {
    "high_score": "Highest score",
    "low_score": "Lowest score",
    "blowout": "Biggest blowout",
    "closest": "Closest game",
    "best_lineup": "Best lineup",
    "worst_lineup": "Most points left on the bench",
    "lucky_win": "Luckiest win",
    "unlucky_loss": "Unluckiest loss",
    "best_benched": "Best player on a bench",
}


@dataclass(frozen=True)
class Award:
    key: str
    label: str
    holder_id: str  # franchise id, or the player id for best_benched
    holder_name: str
    franchise_id: str  # the franchise credited in the tally
    value: float
    unit: str  # pts or pct
    detail: str  # one line; empty when there is nothing to add


def format_value(value: float, unit: str) -> str:
    if unit == "pct":
        return f"{value * 100:.1f}%"
    if unit == "wins":
        return f"{value:+.1f}"
    return f"{value:.1f}"


def labels_with(overrides: dict[str, str] | None) -> dict[str, str]:
    return {**DEFAULT_LABELS, **(overrides or {})}


def _score(value: float | None) -> str:
    return f"{value or 0.0:.1f}"


def _versus(own: Lineup, other: Lineup, other_name: str) -> str:
    own_score, other_score = own.score or 0.0, other.score or 0.0
    verb = "beat" if own_score > other_score else "lost to" if own_score < other_score else "tied"
    return f"{verb} {other_name} {_score(own_score)}–{_score(other_score)}"


def _entries(season: Season, week: int) -> list[tuple[Game, Lineup, Lineup]]:
    """(game, own lineup, opponent lineup) for both sides of every counted game in the week."""
    out: list[tuple[Game, Lineup, Lineup]] = []
    for game in season.games():
        if game.week == week:
            out.append((game, game.home, game.away))
            out.append((game, game.away, game.home))
    return out


def week_awards(league: League, season: Season, week: int, labels: dict[str, str] | None = None) -> list[Award]:
    """Every award with a candidate, in AWARD_KEYS order."""
    names = labels_with(labels)
    entries = _entries(season, week)
    if not entries:
        return []
    year = season.year
    name = {lineup.franchise_id: league.name_in(lineup.franchise_id, year) for _, lineup, _ in entries}
    playoff = week > season.last_regular_season_week
    allplay_record = {row.franchise_id: row.record for row in ([] if playoff else allplay.all_play_week(season, week))}

    def franchise(key: str, own: Lineup, value: float, unit: str, detail: str) -> Award:
        fid = own.franchise_id
        return Award(key, names[key], fid, name[fid], fid, value, unit, detail)

    def best(candidates: list[tuple[float, Lineup, str]], lowest: bool = False) -> tuple[float, Lineup, str] | None:
        """(value, lineup, detail) with the extreme value; ties go to the higher score, then name."""
        if not candidates:
            return None
        sign = 1 if lowest else -1
        return min(candidates, key=lambda c: (sign * c[0], -(c[1].score or 0.0), name[c[1].franchise_id]))

    found: list[Award] = []

    scores = [(own.score or 0.0, own, _versus(own, other, name[other.franchise_id])) for _, own, other in entries]
    if (pick := best(scores)) is not None:
        found.append(franchise("high_score", pick[1], round(pick[0], 1), "pts", pick[2]))
    if (pick := best(scores, lowest=True)) is not None:
        found.append(franchise("low_score", pick[1], round(pick[0], 1), "pts", pick[2]))

    margins: list[tuple[float, Lineup, str]] = []
    for game, own, other in entries:
        if own is game.home:  # one candidate per game, from the winner's side (home on a tie)
            winner = game.winner or game.home
            loser = game.loser or game.away
            if game.tie:
                detail = f"tied with {name[loser.franchise_id]}, {_score(winner.score)}–{_score(loser.score)}"
            else:
                detail = f"over {name[loser.franchise_id]}, {_score(winner.score)}–{_score(loser.score)}"
            margins.append((game.margin, winner, detail))
    if (pick := best(margins)) is not None:
        found.append(franchise("blowout", pick[1], pick[0], "pts", pick[2]))
    if (pick := best(margins, lowest=True)) is not None:
        found.append(franchise("closest", pick[1], pick[0], "pts", pick[2]))

    lineups = [(own, own.opt_pts) for _, own, _ in entries if own.opt_pts]
    efficiency = [((own.score or 0.0) / opt, own, f"{_score(own.score)} of {_score(opt)} possible") for own, opt in lineups]
    if (pick := best(efficiency)) is not None:
        found.append(franchise("best_lineup", pick[1], round(pick[0], 3), "pct", pick[2]))
    left = [(round(opt - (own.score or 0.0), 1), own, f"{_score(own.score)} of {_score(opt)} possible") for own, opt in lineups]
    if (pick := best(left)) is not None:
        found.append(franchise("worst_lineup", pick[1], pick[0], "pts", pick[2]))

    def field_detail(own: Lineup) -> str:
        record = allplay_record.get(own.franchise_id)
        return f"would have gone {record} against the field" if record else ""

    winners = [(own.score or 0.0, own, field_detail(own)) for game, own, _ in entries if game.winner is own]
    if (pick := best(winners, lowest=True)) is not None:
        found.append(franchise("lucky_win", pick[1], round(pick[0], 1), "pts", pick[2]))
    losers = [(own.score or 0.0, own, field_detail(own)) for game, own, _ in entries if game.loser is own]
    if (pick := best(losers)) is not None:
        found.append(franchise("unlucky_loss", pick[1], round(pick[0], 1), "pts", pick[2]))

    benched: list[tuple[float, str, Lineup]] = [
        (own.points(pid), pid, own) for _, own, _ in entries for pid in own.nonstarters if pid in own.scores
    ]
    if benched:
        points, pid, own = min(benched, key=lambda b: (-b[0], season.player(b[1]).name, b[1]))
        fid = own.franchise_id
        found.append(
            Award("best_benched", names["best_benched"], pid, season.player(pid).name, fid, round(points, 1), "pts", f"on {name[fid]}'s bench")
        )

    order = {key: i for i, key in enumerate(AWARD_KEYS)}
    return sorted(found, key=lambda a: order[a.key])


def tally(weeks: Iterable[Iterable[Award]], franchise_ids: Iterable[str]) -> dict[str, dict[str, int]]:
    """franchise id -> award key -> count, with every franchise and key present."""
    counts = {fid: dict.fromkeys(AWARD_KEYS, 0) for fid in franchise_ids}
    for week in weeks:
        for award in week:
            counts.setdefault(award.franchise_id, dict.fromkeys(AWARD_KEYS, 0))[award.key] += 1
    return counts


def leaders(counts: dict[str, dict[str, int]]) -> tuple[tuple[str, ...], int]:
    """(franchise ids sharing the most awards of any kind, that count); ((), 0) when nobody has one."""
    totals = {fid: sum(keyed.values()) for fid, keyed in counts.items()}
    most = max(totals.values(), default=0)
    if most == 0:
        return (), 0
    return tuple(sorted(fid for fid, total in totals.items() if total == most)), most
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/hof/test_hof_awards.py -v`
Expected: 9 passed

- [ ] **Step 5: Lint and commit**

```bash
ruff check hof tests && git add hof/stats/awards.py tests/hof/test_hof_awards.py && git commit -m "hof: weekly awards with tally, leaders, and label overrides"
```

---

### Task 5: Award labels in config

**Files:**
- Modify: `hof/config.py`
- Modify: `data/config.toml` (a commented example)
- Test: `tests/hof/test_hof_config.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/hof/test_hof_config.py`:

```python
def test_award_labels_default_to_empty_and_read_overrides():
    base = {"league": {"id": "1", "site_base_url": "https://x.test/"}}
    assert Config.from_dict(base).award_labels == {}
    config = Config.from_dict({**base, "awards": {"low_score": " Golden Goose Egg ", "worst_lineup": "Armchair QB"}})
    assert config.award_labels == {"low_score": "Golden Goose Egg", "worst_lineup": "Armchair QB"}
    assert Config.load(REPO_CONFIG).award_labels == {}


@pytest.mark.parametrize(
    "awards, message",
    [
        ({"golden_goose": "x"}, "unknown award 'golden_goose'"),
        ({"low_score": "  "}, "empty label"),
    ],
)
def test_bad_award_labels_raise(awards, message):
    with pytest.raises(ConfigError, match=message):
        Config.from_dict({"league": {"id": "1", "site_base_url": "https://x.test/"}, "awards": awards})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/hof/test_hof_config.py -v`
Expected: the two new tests FAIL with `AttributeError: 'Config' object has no attribute 'award_labels'`

- [ ] **Step 3: Extend the config**

In `hof/config.py`:

Change the dataclass import and add the awards import:

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hof.stats.awards import AWARD_KEYS
```

Add the field at the end of `Config` (after `managers`):

```python
    award_labels: dict[str, str] = field(default_factory=dict)  # award key -> display label
```

In `from_dict`, before the final `return`, add:

```python
        labels: dict[str, str] = {}
        for key, label in (raw.get("awards") or {}).items():
            if key not in AWARD_KEYS:
                raise ConfigError(f"awards: unknown award {key!r}; known keys: {', '.join(AWARD_KEYS)}")
            text = str(label).strip()
            if not text:
                raise ConfigError(f"awards: empty label for {key!r}")
            labels[str(key)] = text
```

and change the return to:

```python
        return cls(league_id, base_url, overrides, hall, tuple(managers), labels)
```

In `data/config.toml`, append:

```toml

# Optional display names for the weekly awards; keys are the award keys in hof/stats/awards.py.
# [awards]
# low_score = "Golden Goose Egg"
# worst_lineup = "Armchair Quarterback"
```

- [ ] **Step 4: Run the config tests and the whole suite**

Run: `pytest tests/hof/test_hof_config.py -v && pytest`
Expected: all passed. (`tests/hof/test_hof_site.py` constructs `Config(...)` with keywords and no `award_labels`; the default keeps it working.)

- [ ] **Step 5: Lint and commit**

```bash
ruff check hof tests && git add hof/config.py data/config.toml tests/hof/test_hof_config.py && git commit -m "hof: optional award labels in config"
```

---

### Task 6: Per-season analytics bundle

**Files:**
- Create: `hof/stats/analytics.py`
- Test: `tests/hof/test_hof_analytics.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/hof/test_hof_analytics.py
from synthetic import build_season, four_team_league

from hof.stats import analytics

PLAYERS = {f"a{i}": (f"QB A{i}", "QB") for i in range(1, 5)}


def test_season_analytics_for_2020():
    league = four_team_league()
    season = analytics.season_analytics(league, league.season(2020))
    assert season.year == 2020
    assert [(w.week, w.playoff) for w in season.weeks] == [(1, False), (2, False), (3, True), (4, True)]
    assert [line.name for line in season.weeks[0].standings] == ["Alpha", "Gamma", "Beta", "Delta"]  # through week 1: Beta's 10.0 outscores Delta's 5.0
    assert [line.name for line in season.standings] == ["Gamma", "Alpha", "Delta", "Beta"]  # newest
    assert season.weeks[2].standings == season.weeks[1].standings  # playoff weeks keep the regular-season table
    assert season.weeks[0].power[0].name == "Alpha" and season.weeks[1].power[0].name == "Gamma"
    assert season.weeks[2].power == () and season.weeks[3].power == ()
    assert season.final_power == season.weeks[1].power and season.power_week == 2
    assert [a.key for a in season.weeks[3].awards][:2] == ["high_score", "low_score"]
    assert {fid: sum(c.values()) for fid, c in season.tally.items()} == {"0001": 15, "0002": 4, "0003": 9, "0004": 4}
    assert (season.awards_leaders, season.awards_leader_count) == (("0001",), 15)
    assert (season.luckiest.name, season.luckiest.luck) == ("Delta", 0.7)
    assert (season.unluckiest.name, season.unluckiest.luck) == ("Alpha", -0.7)


def test_in_progress_season_and_label_overrides():
    league = four_team_league()
    season = analytics.season_analytics(league, league.season(2021), {"high_score": "Big Number"})
    assert [w.week for w in season.weeks] == [1]
    assert season.weeks[0].awards[0].label == "Big Number"
    assert [line.name for line in season.final_power] == ["Alpha Prime", "Beta"]
    # both played franchises have luck 0.0; ties go to the name
    assert season.luckiest.name == "Alpha Prime" and season.unluckiest.name == "Alpha Prime"


def test_season_without_games():
    from hof.stats.league import League

    empty = build_season(2022, PLAYERS, {}, last_regular_season_week=2)
    season = analytics.season_analytics(League.build([empty]), empty)
    assert season.weeks == () and season.latest is None and season.standings == ()
    assert season.final_power == () and season.power_week is None
    assert (season.awards_leaders, season.awards_leader_count) == ((), 0)
    assert season.luckiest is None and season.unluckiest is None


def test_compute_covers_every_season():
    league = four_team_league()
    everything = analytics.compute(league)
    assert sorted(everything) == [2020, 2021]
    assert everything[2021].awards_leaders == ("0001",)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/hof/test_hof_analytics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hof.stats.analytics'`

- [ ] **Step 3: Write the module**

```python
# hof/stats/analytics.py
"""Per-season analytics: weekly standings with all-play and luck, power rankings, and awards."""

from __future__ import annotations

from dataclasses import dataclass

from hof.model.season import Season
from hof.stats import allplay, power
from hof.stats import awards as awards_mod
from hof.stats.allplay import StandingLine
from hof.stats.awards import Award
from hof.stats.league import League
from hof.stats.power import PowerLine


@dataclass(frozen=True)
class WeekAnalytics:
    week: int
    playoff: bool
    standings: tuple[StandingLine, ...]  # through this week; through the regular season in playoff weeks
    power: tuple[PowerLine, ...]  # empty in playoff weeks
    awards: tuple[Award, ...]


@dataclass(frozen=True)
class SeasonAnalytics:
    year: int
    weeks: tuple[WeekAnalytics, ...]  # ascending; every week with a counted game
    tally: dict[str, dict[str, int]]  # franchise id -> award key -> count
    awards_leaders: tuple[str, ...]  # franchise ids sharing the most awards
    awards_leader_count: int
    luckiest: StandingLine | None
    unluckiest: StandingLine | None

    @property
    def latest(self) -> WeekAnalytics | None:
        return self.weeks[-1] if self.weeks else None

    @property
    def standings(self) -> tuple[StandingLine, ...]:
        return self.latest.standings if self.latest else ()

    @property
    def final_power(self) -> tuple[PowerLine, ...]:
        """The newest ranking: the last regular-season week's during and after the playoffs."""
        for week in reversed(self.weeks):
            if week.power:
                return week.power
        return ()

    @property
    def power_week(self) -> int | None:
        for week in reversed(self.weeks):
            if week.power:
                return week.week
        return None


def season_analytics(league: League, season: Season, labels: dict[str, str] | None = None) -> SeasonAnalytics:
    weeks: list[WeekAnalytics] = []
    for week in sorted({g.week for g in season.games()}):
        playoff = week > season.last_regular_season_week
        weeks.append(
            WeekAnalytics(
                week=week,
                playoff=playoff,
                standings=tuple(allplay.standings(league, season, None if playoff else week)),
                power=() if playoff else tuple(power.rankings(league, season, week)),
                awards=tuple(awards_mod.week_awards(league, season, week, labels)),
            )
        )
    counts = awards_mod.tally([w.awards for w in weeks], season.franchises)
    leaders, count = awards_mod.leaders(counts)
    played = [line for line in (weeks[-1].standings if weeks else ()) if line.games]
    return SeasonAnalytics(
        year=season.year,
        weeks=tuple(weeks),
        tally=counts,
        awards_leaders=leaders,
        awards_leader_count=count,
        luckiest=min(played, key=lambda line: (-line.luck, line.name), default=None),
        unluckiest=min(played, key=lambda line: (line.luck, line.name), default=None),
    )


def compute(league: League, labels: dict[str, str] | None = None) -> dict[int, SeasonAnalytics]:
    return {season.year: season_analytics(league, season, labels) for season in league.seasons}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/hof/test_hof_analytics.py -v`
Expected: 4 passed

- [ ] **Step 5: Lint and commit**

```bash
ruff check hof tests && git add hof/stats/analytics.py tests/hof/test_hof_analytics.py && git commit -m "hof: per-season analytics bundle"
```

---

### Task 7: Rivalry grid and pair lists

**Files:**
- Create: `hof/stats/rivalries.py`
- Test: `tests/hof/test_hof_rivalries.py`

Synthetic series (from `franchises.all_franchises`): Alpha Prime–Beta 2-0 (2020 wk 1, 2021 wk 1), Alpha Prime–Gamma 1-1, Alpha Prime–Delta 1-0, Beta–Delta 0-1, Beta–Gamma 0-1, Gamma–Delta 1-0. Franchises index order: Gamma (1.000), Alpha Prime (.667), Delta (.500), Beta (.000).

- [ ] **Step 1: Write the failing tests**

```python
# tests/hof/test_hof_rivalries.py
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
    assert [(p.a_name, p.b_name) for p in loose.most_lopsided][:2] == [("Alpha Prime", "Beta"), ("Alpha Prime", "Delta")]
    assert (loose.most_even[0].a_name, loose.most_even[0].b_name, loose.most_even[0].gap) == ("Alpha Prime", "Gamma", 0.0)


def test_pair_leader_line():
    loose = grid(min_meetings=1)
    by_names = {(p.a_name, p.b_name): p for p in loose.most_played}
    assert by_names[("Alpha Prime", "Beta")].leader_line == "Alpha Prime leads Beta 2-0"
    assert by_names[("Beta", "Delta")].leader_line == "Delta leads Beta 1-0"
    assert by_names[("Alpha Prime", "Gamma")].leader_line == "Alpha Prime and Gamma are even at 1-1"
    tie = rivalries.Pair("0001", "A", "0002", "B", 3, 1, 1)
    assert (tie.meetings, tie.record, tie.leader_line, round(tie.gap, 3)) == (5, "3-1-1", "A leads B 3-1-1", 0.2)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/hof/test_hof_rivalries.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hof.stats.rivalries'`

- [ ] **Step 3: Write the module**

```python
# hof/stats/rivalries.py
"""The all-time rivalry grid and the pairs worth talking about."""

from __future__ import annotations

from dataclasses import dataclass

from hof.stats.franchises import FranchiseHistory

MIN_MEETINGS = 5
LIST_SIZE = 5


@dataclass(frozen=True)
class Pair:
    """One unordered pair of franchises, by current names; a is the lower franchise id."""

    a_id: str
    a_name: str
    b_id: str
    b_name: str
    a_wins: int
    b_wins: int
    ties: int

    @property
    def meetings(self) -> int:
        return self.a_wins + self.b_wins + self.ties

    @property
    def gap(self) -> float:
        """Distance of a's win share from .500; 0 is dead even."""
        return abs((self.a_wins + 0.5 * self.ties) / self.meetings - 0.5) if self.meetings else 0.0

    @property
    def record(self) -> str:
        """From a's side, with ties only when there are any."""
        text = f"{self.a_wins}-{self.b_wins}"
        return f"{text}-{self.ties}" if self.ties else text

    @property
    def leader_line(self) -> str:
        if self.a_wins == self.b_wins:
            return f"{self.a_name} and {self.b_name} are even at {self.record}"
        if self.a_wins > self.b_wins:
            return f"{self.a_name} leads {self.b_name} {self.record}"
        flipped = f"{self.b_wins}-{self.a_wins}" + (f"-{self.ties}" if self.ties else "")
        return f"{self.b_name} leads {self.a_name} {flipped}"


@dataclass(frozen=True)
class RivalryGrid:
    order: tuple[str, ...]  # franchise ids in the franchises index order
    cells: dict[tuple[str, str], tuple[int, int, int]]  # (row id, column id) -> row's W, L, T
    most_played: tuple[Pair, ...]
    most_lopsided: tuple[Pair, ...]
    most_even: tuple[Pair, ...]


def ranked(histories: dict[str, FranchiseHistory]) -> list[FranchiseHistory]:
    """The franchises index order: all-time win percentage, then points for, then name."""
    return sorted(histories.values(), key=lambda h: (-h.totals.win_pct, -h.totals.points_for, h.name))


def rivalry_grid(histories: dict[str, FranchiseHistory], min_meetings: int = MIN_MEETINGS) -> RivalryGrid:
    cells: dict[tuple[str, str], tuple[int, int, int]] = {}
    pairs: list[Pair] = []
    for history in histories.values():
        for series in history.series:
            cells[(history.id, series.opponent_id)] = (series.wins, series.losses, series.ties)
            if history.id < series.opponent_id:
                pairs.append(Pair(history.id, history.name, series.opponent_id, series.opponent_name, series.wins, series.losses, series.ties))
    def names(pair: Pair) -> tuple[str, str]:
        return (pair.a_name.casefold(), pair.b_name.casefold())

    most_played = sorted(pairs, key=lambda p: (-p.meetings, names(p)))[:LIST_SIZE]
    eligible = [p for p in pairs if p.meetings >= min_meetings]
    most_lopsided = sorted(eligible, key=lambda p: (-p.gap, -p.meetings, names(p)))[:LIST_SIZE]
    most_even = sorted(eligible, key=lambda p: (p.gap, -p.meetings, names(p)))[:LIST_SIZE]
    return RivalryGrid(
        order=tuple(h.id for h in ranked(histories)),
        cells=cells,
        most_played=tuple(most_played),
        most_lopsided=tuple(most_lopsided),
        most_even=tuple(most_even),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/hof/test_hof_rivalries.py -v`
Expected: 4 passed

- [ ] **Step 5: Lint and commit**

```bash
ruff check hof tests && git add hof/stats/rivalries.py tests/hof/test_hof_rivalries.py && git commit -m "hof: rivalry grid and pair lists"
```

---

### Task 8: Three luck and all-play tables in the records book

**Files:**
- Modify: `hof/stats/records.py` (`TABLES`, `team_season_entries`)
- Modify: `hof/stats/milestones.py` (`_format`)
- Modify: `hof/site/build.py` (the `mark` filter)
- Test: `tests/hof/test_hof_records.py`, `tests/hof/test_hof_milestones.py`

- [ ] **Step 1: Update and add the failing tests**

In `tests/hof/test_hof_records.py`, change the expected key list in `test_every_spec_table_is_present_in_order` so the `"Team, season"` line reads:

```python
        "team_season_high", "team_season_low", "record_best", "streak_win", "streak_loss", "bench_left_season", "efficiency_season",
        "luck_high", "luck_low", "allplay_best",
```

and append:

```python
def test_luck_and_all_play_season_records(book):
    assert book["luck_high"].entries[0] == RecordEntry(0.7, "Delta", "2020, 1-1-0, 0.33 expected wins", 2020, None, False, "0004", None)
    assert [e.holder for e in book["luck_high"].entries] == ["Delta", "Gamma", "Beta", "Alpha"]
    assert book["luck_low"].lowest_first is True
    assert book["luck_low"].entries[0] == RecordEntry(-0.7, "Alpha", "2020, 1-1-0, 1.67 expected wins", 2020, None, False, "0001", None)
    assert book["allplay_best"].entries[0] == RecordEntry(0.833, "Alpha", "5-1-0, 2020", 2020, None, False, "0001", None)
    assert book["allplay_best"].entries[1].holder == "Gamma"  # same .833, ordered by name
    assert all(entry.year == 2020 for key in ("luck_high", "luck_low", "allplay_best") for entry in book[key].entries)
    assert (book["luck_high"].unit, book["allplay_best"].unit) == ("wins", "pct")
```

In `tests/hof/test_hof_milestones.py`, append:

```python
def test_format_signs_luck_in_wins():
    assert milestones._format(0.7, "wins") == "+0.7 wins"
    assert milestones._format(-0.7, "wins") == "-0.7 wins"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/hof/test_hof_records.py tests/hof/test_hof_milestones.py -v`
Expected: `test_every_spec_table_is_present_in_order`, `test_luck_and_all_play_season_records`, and `test_format_signs_luck_in_wins` FAIL

- [ ] **Step 3: Add the tables**

In `hof/stats/records.py`, add the import (ruff's isort places it before `from hof.stats import franchises`; combine as one line):

```python
from hof.stats import allplay, franchises
```

Insert into `TABLES` after the `efficiency_season` line:

```python
    ("luck_high", "Luckiest season", "Team, season", False, "wins"),
    ("luck_low", "Unluckiest season", "Team, season", True, "wins"),
    ("allplay_best", "Best all-play record, season", "Team, season", False, "pct"),
```

In `team_season_entries`, after `if not finished(season): continue`, add:

```python
        lines = {line.franchise_id: line for line in allplay.standings(league, season)}
```

and at the end of the per-franchise loop body (after the `if opt:` block), add:

```python
            line = lines.get(fid)
            if line is not None and line.games:
                luck_detail = f"{year}, {record}, {line.expected_wins:.2f} expected wins"
                out["luck_high"].append(_season_entry(line.luck, row.name, luck_detail, year, fid))
                out["luck_low"].append(_season_entry(line.luck, row.name, luck_detail, year, fid))
                out["allplay_best"].append(_season_entry(round(line.allplay_pct, 3), row.name, f"{line.allplay_record}, {year}", year, fid))
```

In `hof/stats/milestones.py`, in `_format`, add before the `if unit == "pct":` line:

```python
    if unit == "wins":
        return f"{value:+.1f} wins"
```

In `hof/site/build.py`, in the `mark` function inside `environment()`, add before the `if unit == "pct":` line:

```python
        if unit == "wins":
            return f"{value:+.1f}"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/hof/test_hof_records.py tests/hof/test_hof_milestones.py tests/hof/test_hof_site.py -v`
Expected: all passed. `tests/hof/test_hof_model.py::test_compute_bundles_every_stat_for_the_synthetic_league` now fails on `len(model.records) == 24`; Task 9 fixes it.

- [ ] **Step 5: Lint and commit**

```bash
ruff check hof tests && git add hof/stats/records.py hof/stats/milestones.py hof/site/build.py tests/hof/test_hof_records.py tests/hof/test_hof_milestones.py && git commit -m "hof: luckiest, unluckiest, and best all-play season records"
```

---

### Task 9: Wire analytics and rivalries into the model and the CLI

**Files:**
- Modify: `hof/stats/model.py`
- Modify: `hof/__main__.py` (the three `compute(...)` calls and `print_report`)
- Test: `tests/hof/test_hof_model.py`, `tests/hof/test_hof_cli.py`

- [ ] **Step 1: Update and add the failing tests**

In `tests/hof/test_hof_model.py`, change `assert len(model.records) == 24` to `27` and append to that test:

```python
    assert model.analytics[2020].awards_leaders == ("0001",)
    assert model.analytics[2021].final_power[0].name == "Alpha Prime"
    assert model.rivalries.order == ("0003", "0001", "0004", "0002")
    labelled = compute(league.seasons, HallRules(player_min_vor=30, player_min_starts=3, franchise_min_titles=1), {"high_score": "Big Number"})
    assert labelled.analytics[2020].weeks[0].awards[0].label == "Big Number"
```

Append to `test_compute_on_the_real_2020_fixture`:

```python
    season = model.analytics[2020]
    assert len(season.weeks) == 16 and season.power_week == 13
    assert season.weeks[12].power[0].rank == 1 and season.weeks[13].power == ()
    week1 = season.weeks[0].standings
    assert len(week1) == 12 and sum(sum(line.allplay) for line in week1) == 132  # 12 franchises × 11 comparisons
    assert abs(sum(line.luck for line in season.standings)) < 0.6  # raw luck sums to zero; per-line rounding drifts at most 0.05 each
    assert len(season.weeks[0].awards) == 9  # a real week has a benched scorer
    cells = model.rivalries.cells
    assert len(model.rivalries.order) == 12
    assert all(cells[(a, b)][0] == cells[(b, a)][1] for (a, b) in cells)  # symmetric
```

Check `tests/hof/test_hof_cli.py` for a `stats` command test; if `print_report` is exercised there, no change is needed because the report gains only one line. If there is no such test, leave it.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/hof/test_hof_model.py -v`
Expected: FAIL with `AttributeError: 'Model' object has no attribute 'analytics'` (after the records count assertion passes)

- [ ] **Step 3: Extend the model and the CLI**

In `hof/stats/model.py`:

Add imports (keep isort order):

```python
from hof.stats import analytics as analytics_mod
from hof.stats import careers as careers_mod
from hof.stats import drafts as drafts_mod
from hof.stats import franchises as franchises_mod
from hof.stats import hall as hall_mod
from hof.stats import records as records_mod
from hof.stats import rivalries as rivalries_mod
from hof.stats import trades as trades_mod
from hof.stats.analytics import SeasonAnalytics
from hof.stats.careers import Career, WeekKey
from hof.stats.drafts import DraftRanking, DraftSummary
from hof.stats.franchises import FranchiseHistory
from hof.stats.hall import Hall
from hof.stats.league import League
from hof.stats.records import RecordTable
from hof.stats.rivalries import RivalryGrid
from hof.stats.trades import TradeLine
```

Add two fields to `Model` after `champions`:

```python
    analytics: dict[int, SeasonAnalytics]  # by year
    rivalries: RivalryGrid
```

Change `compute` to:

```python
def compute(seasons: list[Season], rules: HallRules, award_labels: dict[str, str] | None = None) -> Model:
    league = League.build(seasons)
    all_stints = careers_mod.roster_stints(league)
    careers = careers_mod.careers(league, all_stints)
    histories = franchises_mod.all_franchises(league)
    records = records_mod.records_book(league, careers)
    drafts = drafts_mod.draft_summaries(league, careers)
    return Model(
        league=league,
        careers=careers,
        histories=histories,
        records=records,
        hall=hall_mod.hall_of_fame(league, careers, histories, rules),
        drafts=drafts,
        draft_rankings=drafts_mod.draft_rankings(league, drafts),
        trades=trades_mod.trade_ledger(league, all_stints),
        through=latest_played_week(league),
        champions=champions(league),
        analytics=analytics_mod.compute(league, award_labels),
        rivalries=rivalries_mod.rivalry_grid(histories),
    )
```

In `hof/__main__.py`, change every `compute(load_all(args.data), config.hall)` (three occurrences: `stats`, `build`, `notify`) to:

```python
compute(load_all(args.data), config.hall, config.award_labels)
```

and in `print_report`, after the `records book` loop, add:

```python
    latest = model.analytics.get(league.latest.year)
    if latest is not None and latest.final_power:
        top = latest.final_power[0]
        print(f"\n{latest.year} power #1 through week {latest.power_week}: {top.name} ({top.score:.3f}); "
              f"awards leader: {', '.join(league.current_name(f) for f in latest.awards_leaders)} ({latest.awards_leader_count})")
```

- [ ] **Step 4: Run the whole suite and lint**

Run: `pytest && ruff check hof tests scripts src`
Expected: all passed, no lint errors.

- [ ] **Step 5: Smoke-test against the real data**

Run: `python -m hof stats | tail -3`
Expected: the last line names the 2026 power number one and the awards leader, for example `2026 power #1 through week 1: ...`. Then run `python -m hof build --out /tmp/hof-check` and confirm it prints `built N pages` with the same page count as before this plan (the records page gains three tables but no new pages).

- [ ] **Step 6: Commit**

```bash
git add hof/stats/model.py hof/__main__.py tests/hof/test_hof_model.py && git commit -m "hof: analytics and rivalries on the model; award labels through the CLI"
```

---

## Done when

- `pytest` passes and `ruff check hof tests scripts src` is clean.
- `Model` exposes `analytics[year]` (weeks with standings, power, awards; tally; leaders; luckiest and unluckiest) and `rivalries` (order, cells, three pair lists).
- `franchises.SeasonRow` and `Totals` carry all-play and luck.
- The records book has 27 tables.
- `config.toml` accepts an optional `[awards]` table and rejects unknown keys.

Plan 2 (`2026-09-08-analytics-2-site.md`) renders all of this and does the mobile rework; Plan 3 (`2026-09-08-analytics-3-discord.md`) adds the second recap embed and the wrap lines.
