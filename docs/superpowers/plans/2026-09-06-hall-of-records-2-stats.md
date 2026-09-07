# Hall of Records, Plan 2 of 4: Stats

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the loaded seasons and per-start values from Plan 1 into every number the site and the Discord posts need: player careers, franchise histories with eras and head-to-head, the records book, Hall of Fame induction, draft hindsight, the trade ledger, and the weekly recap facts, all behind one `compute()` call.

**Architecture:** Pure functions in `hof/stats/`, each module taking a `League` (the seasons plus their `Start` rows) and returning frozen dataclasses. `hof/stats/model.py` runs them all once and bundles the results as a `Model`, which Plans 3 and 4 render. No I/O anywhere in `hof/stats/` except the `stats` command that prints a calibration report.

**Tech Stack:** Python 3.13 dataclasses, pytest with the synthetic season builder from `tests/hof/synthetic.py` and the real 2020 fixture.

**Spec:** `docs/superpowers/specs/2026-09-06-hall-of-records-design.md`, section 6 (all of it), plus the recap inputs in section 8.

---

## What Plan 1 actually built (read this before coding)

Plan 1 landed with a few deviations from its own text; the code is the truth. The signatures below are what this plan codes against.

- `hof.snapshots.load_all(data_dir) -> list[Season]`, oldest first. `load_season` raises on a season with no franchises.
- `hof.model.season.Season` fields: `year, league_id, name, complete, franchises: dict[str, Franchise], starter_minimums, start_week, end_week, last_regular_season_week, weeks: dict[int, Week], bracket: tuple[BracketGame, ...], standings: tuple[Standing, ...], draft: tuple[DraftPick, ...], round1_order, transactions: TransactionLog, players: dict[str, PlayerInfo], bracket_info`. Methods: `player(id) -> PlayerInfo` (never None), `franchise_name(id)`, `games() -> list[Game]` (counted games in week order), `final -> Game | None`, `champion_id -> str | None`, `round_name(i)`, `playoff_weeks()`.
- Round names are `First Round`, `Semifinal`, `Final` (the bracket has byes, so there is no "Quarterfinal").
- `Game`: `year, week, home: Lineup, away: Lineup, playoff, round_name`; `winner`, `loser` (Lineup or None on a tie), `tie`, `margin`, `lineup_of(id)`, `opponent_of(id)`.
- `Lineup`: `franchise_id, starters, nonstarters, scores, score, opt_pts, result`; `played`, `points(id)` (0.0 when unscored).
- `BracketGame`: `week, game_id, round_index, home_id, away_id, home_seed, away_seed`. Seeds 1 and 2 have byes and first appear in round index 1.
- `Standing`: `franchise_id, wins, losses, ties, points_for, points_against, division_record, streak`, in MFL's standings order.
- `DraftPick`: `round, pick, franchise_id, player_id, timestamp, comments`.
- `TransactionLog`: `trades, waivers, free_agents, roster_moves, lock_times`; `effective_week(timestamp, start_week) -> int | None` (None once the season's last lock has passed, or when the season has no locks at all).
- `Trade`: `timestamp, franchise1, franchise2, gave_up1, gave_up2, comments`. `WaiverClaim`: `timestamp, franchise, added, bid, dropped`. `FreeAgentMove`: `timestamp, franchise, added, dropped`.
- `hof.stats.vor.starts(season) -> list[Start]`; `Start`: `year, week, franchise_id, player_id, position, points, vor, playoff`.
- `hof.model.season.normalize_name(name)` casefolds and collapses whitespace.
- `hof.config.HallRules`: `player_min_vor, player_min_starts, franchise_min_titles, watch_list_margin`.
- Tests import the builders with `from synthetic import build_season, lineup`; `build_season(year, players, weeks, last_regular_season_week, franchises=..., bracket=..., starter_minimums=..., complete=..., transactions=..., names=...)` where `players` maps id to `(name, position)` and `weeks` maps week number to `[(home Lineup, away Lineup), ...]`; `lineup(franchise_id, starters: dict[id, score], bench=None, opt_pts=None)`.

## Facts from the real backfill that shape the design

- Eleven seasons. 2016 (league 79873) has a 300-pick startup draft, no transaction log at all, and therefore no lock times. 2026 has its draft and 19 offseason trades but, at the time of writing, no played week.
- Every season has 12 franchises, 12 lineups listed every week including playoff weeks, a 6-team bracket of 3 rounds and 5 games, and `lastRegularSeasonWeek` 13 through 2020 and 14 from 2021. Finals are in week 16 through 2020 and week 17 after.
- Champions: 2016 0003, 2017 0010, 2018 0007, 2019 0011, 2020 0010, 2021 0006, 2022 0003, 2023 0003, 2024 0006, 2025 0001.
- Name eras exist for five franchises; 0011 has four (`Greek Invasion`, `Ezekiel 23:20`, `Half Chubb`, `Second Stringers Anonymous`). No name was ever used by two franchises.
- 714 distinct starters; every start is QB, RB, WR, or TE, and every started player id is in its season's players snapshot.
- Career value over replacement with at least 30 starts: 63 players clear 400, 44 clear 500, 34 clear 600. Mahomes leads at about 1,600. The config default of 400 would induct 63 players; the calibration step in Task 9 prints these counts so the owner can pick.
- 250 trades; asset codes are only player ids, `BB_`, `FP_`, and `DP_`. 23 trades fall after their season's last lock (offseason), so they take effect in the next season's week 1.
- Draft pick comments look like `[Pick traded from Suck My Ditka.\nPick traded from Second Stringers Anonymous.\nPick made by Commissioner.]`, sometimes without the brackets. The first `Pick traded from` name is the original owner; matching that name against every name any franchise has ever used resolves all 250 traded future picks whose draft has happened to exactly one pick each. Names can contain periods (`D.K. Mudbone`), so parse by line, not by regex on periods.
- In 2019 one player appears on two rosters in the same week (a mid-week trade). Stint logic must tolerate a player being on more than one roster in a week.

## Conventions

Same as Plan 1: run from the repo root with the virtualenv active, `pytest` for tests, `ruff check src tests scripts hof` for lint, commit after every task with the `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` trailer. New test files are `tests/hof/test_hof_<module>.py`. Every stats function is pure: no file or network access.

## File structure

| Path | Responsibility |
|---|---|
| `hof/stats/league.py` | `League`: seasons plus starts, current names, eras, player lookup, roster membership |
| `hof/stats/careers.py` | stints, season lines, arrivals and departures, `Career` |
| `hof/stats/franchises.py` | season rows, finishes, era and all-time totals, streaks, head-to-head, `FranchiseHistory` |
| `hof/stats/records.py` | the records book |
| `hof/stats/hall.py` | induction, plaques, watch list |
| `hof/stats/drafts.py` | original owners from pick comments, hindsight, steals and busts, rankings |
| `hof/stats/trades.py` | asset resolution, attribution by effective week, verdicts |
| `hof/stats/milestones.py` | recap facts for one completed week, season awards for the wrap |
| `hof/stats/model.py` | `compute(seasons, rules) -> Model` |
| `hof/__main__.py` | gains `stats`, a calibration report |
| `tests/hof/synthetic.py` | gains `draft` and `standings` parameters |
| `tests/hof/test_hof_<module>.py` | one per module |

---

### Task 1: `League` and roster membership

**Files:**
- Create: `hof/stats/league.py`
- Modify: `tests/hof/synthetic.py`
- Test: `tests/hof/test_hof_league.py`

- [ ] **Step 1: Extend the synthetic builder**

In `tests/hof/synthetic.py`, add two parameters to `build_season` and pass them through. Change the signature to:

```python
def build_season(
    year: int,
    players: dict[str, tuple[str, str]],
    weeks: dict[int, list[tuple[Lineup, Lineup]]],
    last_regular_season_week: int,
    franchises: tuple[str, ...] = ("0001", "0002", "0003", "0004"),
    bracket: tuple[BracketGame, ...] = (),
    starter_minimums: dict[str, int] | None = None,
    complete: bool = True,
    transactions: TransactionLog | None = None,
    names: dict[str, str] | None = None,
    draft: tuple[DraftPick, ...] = (),
    standings: tuple[Standing, ...] = (),
) -> Season:
```

and in the returned `Season(...)` replace `standings=(),` with `standings=standings,` and `draft=(),` with `draft=draft,`. Extend the import line to `from hof.model.season import BracketGame, DraftPick, Franchise, Lineup, Season, Standing, Week`.

Run: `pytest tests/hof -q`
Expected: everything still passes.

- [ ] **Step 2: Write the failing tests**

`tests/hof/test_hof_league.py`:

```python
from synthetic import build_season, lineup

from hof.model.players import PlayerInfo
from hof.stats.league import Era, League

PLAYERS = {"q1": ("QB One", "QB"), "q2": ("QB Two", "QB"), "r1": ("RB One", "RB")}


def two_seasons():
    s1 = build_season(
        2020,
        PLAYERS,
        {1: [(lineup("0001", {"q1": 20.0}, bench={"r1": 4.0}), lineup("0002", {"q2": 10.0}))]},
        last_regular_season_week=1,
        franchises=("0001", "0002"),
        names={"0001": "Old Name", "0002": "Team Two"},
    )
    s2 = build_season(
        2021,
        PLAYERS,
        {1: [(lineup("0001", {"q1": 15.0}), lineup("0002", {"q2": 25.0}, bench={"r1": 1.0}))]},
        last_regular_season_week=1,
        franchises=("0001", "0002"),
        names={"0001": "New  Name", "0002": "team two"},
    )
    return League.build([s1, s2])


def test_build_computes_starts_per_season():
    league = two_seasons()
    assert [s.year for s in league.seasons] == [2020, 2021]
    assert {year: len(rows) for year, rows in league.starts.items()} == {2020: 2, 2021: 2}
    assert len(league.all_starts()) == 4
    assert league.latest.year == 2021
    assert league.season(2020).year == 2020


def test_current_name_and_eras_ignore_cosmetic_renames():
    league = two_seasons()
    assert league.franchise_ids() == ["0001", "0002"]
    assert league.current_name("0001") == "New  Name"
    assert league.name_in("0001", 2020) == "Old Name"
    assert league.eras("0001") == [Era("0001", "Old Name", 2020, 2020), Era("0001", "New  Name", 2021, 2021)]
    # "Team Two" and "team two" differ only by case, so they are one era named by the newest spelling
    assert league.eras("0002") == [Era("0002", "team two", 2020, 2021)]
    assert league.era_of("0002", 2020).name == "team two"


def test_player_info_prefers_the_newest_season():
    s1 = build_season(2020, {"p": ("Old Spelling", "WR")}, {1: [(lineup("0001", {"p": 1.0}), lineup("0002", {}))]}, 1, franchises=("0001", "0002"))
    s2 = build_season(2021, {"p": ("New Spelling", "WR")}, {}, 1, franchises=("0001", "0002"))
    league = League.build([s1, s2])
    assert league.player_info("p").name == "New Spelling"
    assert league.player_info("zzz") == PlayerInfo.unknown("zzz")


def test_rosters_track_starters_and_bench_by_week():
    league = two_seasons()
    rosters = league.rosters(2020)
    assert rosters == {1: {"q1": {"0001"}, "r1": {"0001"}, "q2": {"0002"}}}
    assert league.latest_rostered_week() == (2021, 1)


def test_completed_and_name_lookup():
    league = two_seasons()
    assert [s.year for s in league.completed()] == [2020, 2021]
    assert league.franchise_by_name() == {"old name": "0001", "new name": "0001", "team two": "0002"}
```

- [ ] **Step 3: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_league.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'hof.stats.league'`.

- [ ] **Step 4: Implement**

`hof/stats/league.py`:

```python
"""The whole league: every season plus its Start rows, and the cross-season lookups."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from hof.model.players import PlayerInfo
from hof.model.season import Season, normalize_name
from hof.stats.vor import Start, starts


@dataclass(frozen=True)
class Era:
    """A run of consecutive seasons in which a franchise kept one name (ignoring cosmetics)."""

    franchise_id: str
    name: str  # the newest spelling used in the era
    first_year: int
    last_year: int


@dataclass
class League:
    seasons: list[Season]  # ascending by year
    starts: dict[int, list[Start]] = field(default_factory=dict)  # year -> starts

    @classmethod
    def build(cls, seasons: list[Season]) -> League:
        ordered = sorted(seasons, key=lambda s: s.year)
        return cls(ordered, {s.year: starts(s) for s in ordered})

    # --- seasons -------------------------------------------------------------

    @property
    def latest(self) -> Season:
        return self.seasons[-1]

    def season(self, year: int) -> Season:
        for season in self.seasons:
            if season.year == year:
                return season
        raise KeyError(year)

    def completed(self) -> list[Season]:
        return [s for s in self.seasons if s.complete]

    def all_starts(self) -> list[Start]:
        return [row for season in self.seasons for row in self.starts[season.year]]

    # --- franchises ----------------------------------------------------------

    def franchise_ids(self) -> list[str]:
        return sorted({fid for s in self.seasons for fid in s.franchises})

    def name_in(self, franchise_id: str, year: int) -> str:
        """The name the franchise used in that season, or its current name when it did not exist."""
        season = self.season(year)
        franchise = season.franchises.get(franchise_id)
        return franchise.name if franchise else self.current_name(franchise_id)

    def current_name(self, franchise_id: str) -> str:
        for season in reversed(self.seasons):
            franchise = season.franchises.get(franchise_id)
            if franchise:
                return franchise.name
        return f"Franchise {franchise_id}"

    def eras(self, franchise_id: str) -> list[Era]:
        eras: list[Era] = []
        for season in self.seasons:
            franchise = season.franchises.get(franchise_id)
            if franchise is None:
                continue
            if eras and normalize_name(eras[-1].name) == normalize_name(franchise.name):
                eras[-1] = Era(franchise_id, franchise.name, eras[-1].first_year, season.year)
            else:
                eras.append(Era(franchise_id, franchise.name, season.year, season.year))
        return eras

    def era_of(self, franchise_id: str, year: int) -> Era:
        for era in self.eras(franchise_id):
            if era.first_year <= year <= era.last_year:
                return era
        raise KeyError((franchise_id, year))

    def franchise_by_name(self) -> dict[str, str]:
        """Normalized name -> franchise id, over every name ever used."""
        lookup: dict[str, str] = {}
        for season in self.seasons:
            for fid, franchise in season.franchises.items():
                lookup[normalize_name(franchise.name)] = fid
        return lookup

    # --- players -------------------------------------------------------------

    def player_info(self, player_id: str) -> PlayerInfo:
        for season in reversed(self.seasons):
            info = season.players.get(player_id)
            if info is not None:
                return info
        return PlayerInfo.unknown(player_id)

    def rosters(self, year: int) -> dict[int, dict[str, set[str]]]:
        """week -> player id -> franchises whose starters or bench listed the player."""
        out: dict[int, dict[str, set[str]]] = {}
        for number, week in sorted(self.season(year).weeks.items()):
            members: dict[str, set[str]] = defaultdict(set)
            for lineup in week.lineups.values():
                for player_id in lineup.starters + lineup.nonstarters:
                    members[player_id].add(lineup.franchise_id)
            if members:
                out[number] = dict(members)
        return out

    def latest_rostered_week(self) -> tuple[int, int] | None:
        """The newest (year, week) with any roster listed; None when no season has one."""
        for season in reversed(self.seasons):
            weeks = self.rosters(season.year)
            if weeks:
                return season.year, max(weeks)
        return None
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/hof/test_hof_league.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add hof/stats/league.py tests/hof/synthetic.py tests/hof/test_hof_league.py
git commit -m "feat(hof): League with eras, names, and roster membership

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Player careers

**Files:**
- Create: `hof/stats/careers.py`
- Test: `tests/hof/test_hof_careers.py`

- [ ] **Step 1: Write the failing tests**

`tests/hof/test_hof_careers.py`:

```python
from synthetic import build_season, lineup

from hof.model.season import BracketGame, DraftPick
from hof.model.transactions import FreeAgentMove, Trade, TransactionLog, WaiverClaim
from hof.stats import careers
from hof.stats.league import League

PLAYERS = {
    "q1": ("QB One", "QB"),
    "q2": ("QB Two", "QB"),
    "r1": ("RB One", "RB"),
    "r2": ("RB Two", "RB"),
    "rk": ("Rookie Back", "RB"),
}
LOCKS = (100, 200, 300)  # weeks 1, 2, 3 lock at these timestamps


def league_with_moves():
    """2020: r1 starts on 0001, is traded to 0002 after week 1; rk is drafted by 0002 and claimed
    by 0001 on waivers before week 3; q2 is dropped after week 2. 2021: r1 stays on 0002."""
    log_2020 = TransactionLog(
        trades=(Trade(150, "0001", "0002", ("r1",), ("BB_5",), ""),),
        waivers=(WaiverClaim(250, "0001", "rk", "12.00", None),),
        free_agents=(FreeAgentMove(260, "0002", (), ("q2",)),),
        roster_moves=(),
        lock_times=LOCKS,
    )
    s2020 = build_season(
        2020,
        PLAYERS,
        {
            1: [(lineup("0001", {"q1": 20.0, "r1": 10.0}), lineup("0002", {"q2": 15.0, "r2": 8.0}, bench={"rk": 3.0}))],
            2: [(lineup("0002", {"q2": 12.0, "r1": 14.0}, bench={"rk": 6.0}), lineup("0001", {"q1": 9.0, "r2": 0.0}))],
            3: [(lineup("0001", {"q1": 30.0, "rk": 11.0}), lineup("0002", {"r1": 7.0, "r2": 2.0}))],
        },
        last_regular_season_week=2,
        franchises=("0001", "0002"),
        bracket=(BracketGame(3, "1", 0, "0001", "0002", 1, 2),),
        transactions=log_2020,
        draft=(DraftPick(1, 1, "0002", "rk", 50),),
        names={"0001": "Alpha", "0002": "Beta"},
    )
    s2021 = build_season(
        2021,
        PLAYERS,
        {1: [(lineup("0002", {"r1": 20.0}), lineup("0001", {"q1": 5.0, "rk": 9.0}))]},
        last_regular_season_week=1,
        franchises=("0001", "0002"),
        complete=False,
        names={"0001": "Alpha", "0002": "Beta"},
    )
    return League.build([s2020, s2021])


def test_stints_follow_roster_membership_across_seasons():
    league = league_with_moves()
    stints = careers.stints(league)
    assert stints["r1"] == [
        careers.Stint("r1", "0001", (2020, 1), (2020, 1)),
        careers.Stint("r1", "0002", (2020, 2), (2021, 1)),
    ]
    assert stints["rk"] == [
        careers.Stint("rk", "0002", (2020, 1), (2020, 2)),
        careers.Stint("rk", "0001", (2020, 3), (2021, 1)),
    ]
    assert stints["q2"] == [careers.Stint("q2", "0002", (2020, 1), (2020, 2))]


def test_moves_are_matched_to_transactions_and_the_draft():
    league = league_with_moves()
    moves = {pid: c.moves for pid, c in careers.careers(league).items()}
    assert moves["r1"] == (
        careers.Move("joined", 2020, 1, "0001"),
        careers.Move("traded away", 2020, 1, "0001", "to Beta"),
        careers.Move("traded", 2020, 2, "0002", "from Alpha"),
    )
    assert moves["rk"] == (
        careers.Move("drafted", 2020, 1, "0002", "Round 1, Pick 1"),
        careers.Move("left", 2020, 2, "0002"),
        careers.Move("claimed", 2020, 3, "0001", "$12"),
    )
    assert moves["q2"] == (
        careers.Move("joined", 2020, 1, "0002"),
        careers.Move("dropped", 2020, 2, "0002"),
    )


def test_season_lines_and_career_totals():
    league = league_with_moves()
    r1 = careers.careers(league)["r1"]
    assert r1.name == "RB One" and r1.position == "RB"
    assert [line.year for line in r1.seasons] == [2020, 2021]
    line = r1.seasons[0]
    assert line.franchise_ids == ("0001", "0002")
    assert (line.starts, line.points) == (3, 31.0)
    assert (line.playoff_starts, line.playoff_points) == (1, 7.0)
    assert line.title is False
    assert r1.seasons[1].title is False
    assert (r1.starts, r1.points, r1.playoff_starts) == (4, 51.0, 1)
    assert r1.franchise_ids == ("0001", "0002")
    assert (r1.first_year, r1.last_year, r1.active) == (2020, 2021, True)
    q2 = careers.careers(league)["q2"]
    assert q2.active is False
    assert q2.last_year == 2020


def test_bench_points_and_titles():
    league = league_with_moves()
    rk = careers.careers(league)["rk"]
    assert rk.seasons[0].bench_points == 9.0  # 3.0 in week 1 plus 6.0 in week 2, both counted games
    assert rk.seasons[0].title is True  # started for 0001, the 2020 champion, in the final
    assert rk.titles == 1
    q1 = careers.careers(league)["q1"]
    assert q1.titles == 1
    assert careers.careers(league)["q2"].titles == 0


def test_players_without_a_start_are_excluded():
    league = league_with_moves()
    s = build_season(2022, {"b": ("Bench Only", "WR")}, {1: [(lineup("0001", {}, bench={"b": 5.0}), lineup("0002", {}))]}, 1, franchises=("0001", "0002"))
    league = League.build(league.seasons + [s])
    assert "b" not in careers.careers(league)


def test_effective_key_maps_offseason_trades_to_next_season():
    league = league_with_moves()
    season = league.season(2020)
    assert careers.effective_key(season, 150) == (2020, 2)
    assert careers.effective_key(season, 99) == (2020, 1)
    assert careers.effective_key(season, 999) == (2021, 0)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_careers.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'hof.stats.careers'`.

- [ ] **Step 3: Implement**

`hof/stats/careers.py`:

```python
"""Player careers: roster stints, per-season lines, and how each stint began and ended."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from bdfl.assets import format_dollars
from hof.model.season import Season
from hof.stats.league import League

WeekKey = tuple[int, int]  # (year, week); (year, 0) means "before week 1 of year"


@dataclass(frozen=True)
class Stint:
    player_id: str
    franchise_id: str
    start: WeekKey  # first rostered week
    end: WeekKey  # last rostered week


@dataclass(frozen=True)
class Move:
    kind: str  # drafted, traded, claimed, signed, joined, traded away, dropped, left
    year: int
    week: int
    franchise_id: str
    detail: str = ""


@dataclass(frozen=True)
class SeasonLine:
    year: int
    franchise_ids: tuple[str, ...]  # every franchise rostering the player that season, first seen first
    starts: int
    points: float
    vor: float
    bench_points: float
    playoff_starts: int
    playoff_points: float
    title: bool  # started for the champion in the final


@dataclass(frozen=True)
class Career:
    player_id: str
    name: str
    position: str
    first_year: int
    last_year: int
    active: bool  # on a roster in the newest rostered week
    seasons: tuple[SeasonLine, ...]
    stints: tuple[Stint, ...]
    moves: tuple[Move, ...]
    starts: int
    points: float
    vor: float
    bench_points: float
    playoff_starts: int
    playoff_points: float
    titles: int
    franchise_ids: tuple[str, ...]  # in order of first stint


@dataclass(frozen=True)
class Transfer:
    """A transaction that put a player on (adding) or took one off (removing) a franchise."""

    key: WeekKey
    kind: str
    franchise_id: str
    detail: str


def effective_key(season: Season, timestamp: int) -> WeekKey:
    """The (year, week) a transaction takes effect; (year + 1, 0) once the season's locks are past."""
    week = season.transactions.effective_week(timestamp, season.start_week)
    return (season.year, week) if week is not None else (season.year + 1, 0)


Rosters = dict[int, dict[int, dict[str, set[str]]]]  # year -> week -> player id -> franchises


def rosters_by_year(league: League) -> Rosters:
    """Computed once per run because League.rosters() rebuilds its answer on every call."""
    return {season.year: league.rosters(season.year) for season in league.seasons}


def following_weeks(rosters: Rosters) -> dict[WeekKey, WeekKey]:
    """Each rostered (year, week) -> the next rostered one; the newest week has no entry."""
    keys = [(year, week) for year in sorted(rosters) for week in sorted(rosters[year])]
    return dict(zip(keys, keys[1:], strict=False))


def stints(league: League, rosters: Rosters | None = None) -> dict[str, list[Stint]]:
    """Runs of consecutive rostered weeks per player and franchise; the offseason does not break a run."""
    rosters = rosters if rosters is not None else rosters_by_year(league)
    open_: dict[tuple[str, str], Stint] = {}
    done: dict[str, list[Stint]] = defaultdict(list)
    for season in league.seasons:
        weeks = rosters[season.year]
        for week in sorted(weeks):
            current = {(pid, fid) for pid, fids in weeks[week].items() for fid in fids}
            for key in list(open_):
                if key not in current:
                    done[key[0]].append(open_.pop(key))
            for pid, fid in current:
                previous = open_.get((pid, fid))
                start = previous.start if previous else (season.year, week)
                open_[(pid, fid)] = Stint(pid, fid, start, (season.year, week))
    for (pid, _), stint in open_.items():
        done[pid].append(stint)
    return {pid: sorted(rows, key=lambda s: s.start) for pid, rows in done.items()}


def transfers(league: League) -> tuple[dict[str, list[Transfer]], dict[str, list[Transfer]]]:
    """(adding, removing) transfers per player id, from every season's transaction log."""
    adding: dict[str, list[Transfer]] = defaultdict(list)
    removing: dict[str, list[Transfer]] = defaultdict(list)
    for season in league.seasons:
        log = season.transactions
        for trade in log.trades:
            key = effective_key(season, trade.timestamp)
            name1, name2 = season.franchise_name(trade.franchise1), season.franchise_name(trade.franchise2)
            for pid in trade.gave_up1:
                if pid.isalnum():
                    removing[pid].append(Transfer(key, "traded away", trade.franchise1, f"to {name2}"))
                    adding[pid].append(Transfer(key, "traded", trade.franchise2, f"from {name1}"))
            for pid in trade.gave_up2:
                if pid.isalnum():
                    removing[pid].append(Transfer(key, "traded away", trade.franchise2, f"to {name1}"))
                    adding[pid].append(Transfer(key, "traded", trade.franchise1, f"from {name2}"))
        for claim in log.waivers:
            key = effective_key(season, claim.timestamp)
            adding[claim.added].append(Transfer(key, "claimed", claim.franchise, format_dollars(claim.bid)))
            if claim.dropped:
                removing[claim.dropped].append(Transfer(key, "dropped", claim.franchise, ""))
        for move in log.free_agents:
            key = effective_key(season, move.timestamp)
            for pid in move.added:
                adding[pid].append(Transfer(key, "signed", move.franchise, ""))
            for pid in move.dropped:
                removing[pid].append(Transfer(key, "dropped", move.franchise, ""))
    return adding, removing


def _drafted(league: League, stint: Stint) -> Move | None:
    season = league.season(stint.start[0])
    for pick in season.draft:
        if pick.player_id == stint.player_id and pick.franchise_id == stint.franchise_id:
            return Move("drafted", season.year, stint.start[1], stint.franchise_id, f"Round {pick.round}, Pick {pick.pick}")
    return None


def moves_for(
    league: League,
    player_stints: list[Stint],
    adding: list[Transfer],
    removing: list[Transfer],
    following: dict[WeekKey, WeekKey],
) -> tuple[Move, ...]:
    moves: list[Move] = []
    previous_end: dict[str, WeekKey] = {}
    for stint in player_stints:
        floor = previous_end.get(stint.franchise_id, (0, 0))
        arrivals = [t for t in adding if t.franchise_id == stint.franchise_id and floor < t.key <= stint.start]
        drafted = _drafted(league, stint) if stint.franchise_id not in previous_end else None
        if arrivals:
            latest = max(arrivals, key=lambda t: t.key)
            moves.append(Move(latest.kind, stint.start[0], stint.start[1], stint.franchise_id, latest.detail))
        elif drafted is not None:
            moves.append(drafted)
        else:
            moves.append(Move("joined", stint.start[0], stint.start[1], stint.franchise_id))
        after = following.get(stint.end)
        if after is not None:
            departures = [t for t in removing if t.franchise_id == stint.franchise_id and stint.end < t.key <= after]
            if departures:
                first = min(departures, key=lambda t: t.key)
                moves.append(Move(first.kind, stint.end[0], stint.end[1], stint.franchise_id, first.detail))
            else:
                moves.append(Move("left", stint.end[0], stint.end[1], stint.franchise_id))
        previous_end[stint.franchise_id] = stint.end
    return tuple(moves)


def bench_points(season: Season) -> dict[str, float]:
    """Player id -> points scored on the bench in counted games this season."""
    totals: dict[str, float] = defaultdict(float)
    for game in season.games():
        for lineup in (game.home, game.away):
            for pid in lineup.nonstarters:
                totals[pid] += lineup.points(pid)
    return {pid: round(v, 1) for pid, v in totals.items()}


def title_starters(season: Season) -> set[str]:
    final = season.final
    if final is None or final.winner is None:
        return set()
    return set(final.winner.starters)


def careers(league: League) -> dict[str, Career]:
    """Every player with at least one counted start, keyed by player id."""
    rosters = rosters_by_year(league)
    following = following_weeks(rosters)
    all_stints = stints(league, rosters)
    adding, removing = transfers(league)
    newest = league.latest_rostered_week()
    by_player_year: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    for row in league.all_starts():
        by_player_year[row.player_id][row.year].append(row)
    bench_by_year = {s.year: bench_points(s) for s in league.seasons}
    titles_by_year = {s.year: title_starters(s) for s in league.seasons}
    rostered_by_year: dict[int, dict[str, list[str]]] = {}
    for season in league.seasons:
        seen: dict[str, list[str]] = defaultdict(list)
        for week in sorted(rosters[season.year]):
            for pid, fids in rosters[season.year][week].items():
                for fid in sorted(fids):
                    if fid not in seen[pid]:
                        seen[pid].append(fid)
        rostered_by_year[season.year] = seen

    result: dict[str, Career] = {}
    for pid, by_year in by_player_year.items():
        lines: list[SeasonLine] = []
        for season in league.seasons:
            rows = by_year.get(season.year, [])
            rostered = rostered_by_year[season.year].get(pid, [])
            if not rows and not rostered:
                continue
            lines.append(
                SeasonLine(
                    year=season.year,
                    franchise_ids=tuple(rostered),
                    starts=len(rows),
                    points=round(sum(r.points for r in rows), 1),
                    vor=round(sum(r.vor for r in rows), 1),
                    bench_points=bench_by_year[season.year].get(pid, 0.0),
                    playoff_starts=sum(1 for r in rows if r.playoff),
                    playoff_points=round(sum(r.points for r in rows if r.playoff), 1),
                    title=pid in titles_by_year[season.year],
                )
            )
        player_stints = all_stints.get(pid, [])
        info = league.player_info(pid)
        franchise_order: list[str] = []
        for stint in player_stints:
            if stint.franchise_id not in franchise_order:
                franchise_order.append(stint.franchise_id)
        result[pid] = Career(
            player_id=pid,
            name=info.name,
            position=info.position,
            first_year=lines[0].year,
            last_year=lines[-1].year,
            active=bool(player_stints) and newest is not None and player_stints[-1].end == newest,
            seasons=tuple(lines),
            stints=tuple(player_stints),
            moves=moves_for(league, player_stints, adding.get(pid, []), removing.get(pid, []), following),
            starts=sum(line.starts for line in lines),
            points=round(sum(line.points for line in lines), 1),
            vor=round(sum(line.vor for line in lines), 1),
            bench_points=round(sum(line.bench_points for line in lines), 1),
            playoff_starts=sum(line.playoff_starts for line in lines),
            playoff_points=round(sum(line.playoff_points for line in lines), 1),
            titles=sum(1 for line in lines if line.title),
            franchise_ids=tuple(franchise_order),
        )
    return result
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/hof/test_hof_careers.py -v`
Expected: 6 passed. If `test_moves_are_matched_to_transactions_and_the_draft` fails on `rk`, check the order of the three moves: the draft arrival, then `left` at (2020, 2) because the waiver log has no drop by 0002 (the claim came from 0001), then `claimed` at week 3.

- [ ] **Step 5: Lint and commit**

Run: `ruff check hof tests/hof`
Expected: no issues.

```bash
git add hof/stats/careers.py tests/hof/test_hof_careers.py
git commit -m "feat(hof): player careers with stints, season lines, and moves

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Franchise histories

**Files:**
- Create: `hof/stats/franchises.py`
- Test: `tests/hof/test_hof_franchises.py`

- [ ] **Step 1: Write the failing tests**

`tests/hof/test_hof_franchises.py`:

```python
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
    assert r2020.top_starter == ("a1", "QB A1", 87.0, 48.0)
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
    assert (a1.name, a1.position, a1.first_year, a1.last_year, a1.starts, a1.points, a1.vor) == ("QB A1", "QB", 2020, 2021, 5, 97.0, 53.0)


def test_all_franchises_covers_every_id():
    assert sorted(franchises.all_franchises(league())) == ["0001", "0002", "0003", "0004"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_franchises.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'hof.stats.franchises'`.

- [ ] **Step 3: Implement**

`hof/stats/franchises.py`:

```python
"""Franchise histories: season rows and finishes, era and all-time totals, streaks, head-to-head."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from hof.model.season import Lineup, Season
from hof.stats.league import Era, League


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

    @property
    def win_pct(self) -> float:
        return (self.wins + 0.5 * self.ties) / self.games if self.games else 0.0

    @property
    def record(self) -> str:
        return f"{self.wins}-{self.losses}-{self.ties}"


@dataclass(frozen=True)
class SeasonRow:
    year: int
    name: str  # the name used that season
    wins: int
    losses: int
    ties: int
    division_record: str
    points_for: float
    points_against: float
    seed: int | None
    playoff_wins: int
    playoff_losses: int
    finish: str
    title: bool
    in_progress: bool
    top_starter: tuple[str, str, float, float] | None  # (player id, name, points, vor)


@dataclass(frozen=True)
class EraSummary:
    era: Era
    rows: tuple[SeasonRow, ...]  # newest first
    totals: Totals


@dataclass(frozen=True)
class Meeting:
    """One counted game from one franchise's point of view."""

    year: int
    week: int
    playoff: bool
    round_name: str | None
    own_name: str
    opponent_id: str
    opponent_name: str
    own_score: float
    opponent_score: float
    result: str  # W, L, or T


@dataclass(frozen=True)
class Series:
    opponent_id: str
    opponent_name: str  # current name
    wins: int
    losses: int
    ties: int
    regular: tuple[int, int, int]
    playoff: tuple[int, int, int]
    points_for: float
    points_against: float
    avg_margin: float
    streak: str
    last: Meeting | None
    meetings: tuple[Meeting, ...]  # oldest first


@dataclass(frozen=True)
class TopStarter:
    player_id: str
    name: str
    position: str
    first_year: int
    last_year: int
    starts: int
    points: float
    vor: float


@dataclass(frozen=True)
class FranchiseHistory:
    id: str
    name: str  # current name
    eras: tuple[EraSummary, ...]  # newest first
    totals: Totals
    streak: str
    longest_win_streak: int
    longest_loss_streak: int
    best_season: SeasonRow | None
    worst_season: SeasonRow | None
    series: tuple[Series, ...]  # by opponent's current name
    top_starters: tuple[TopStarter, ...]  # by vor, descending
    playoff_games: tuple[Meeting, ...]  # newest first


def _result(own: Lineup, opponent: Lineup) -> str:
    own_score, opponent_score = own.score or 0.0, opponent.score or 0.0
    if own_score == opponent_score:
        return "T"
    return "W" if own_score > opponent_score else "L"


def meetings(league: League, season: Season, franchise_id: str) -> list[Meeting]:
    rows: list[Meeting] = []
    for game in season.games():
        own, opponent = game.lineup_of(franchise_id), game.opponent_of(franchise_id)
        if own is None or opponent is None:
            continue
        rows.append(
            Meeting(
                year=season.year,
                week=game.week,
                playoff=game.playoff,
                round_name=game.round_name,
                own_name=league.name_in(franchise_id, season.year),
                opponent_id=opponent.franchise_id,
                opponent_name=league.name_in(opponent.franchise_id, season.year),
                own_score=own.score or 0.0,
                opponent_score=opponent.score or 0.0,
                result=_result(own, opponent),
            )
        )
    return rows


def _seed(season: Season, franchise_id: str) -> int | None:
    for game in season.bracket:
        if game.home_id == franchise_id and game.home_seed is not None:
            return game.home_seed
        if game.away_id == franchise_id and game.away_seed is not None:
            return game.away_seed
    return None


def _finish(season: Season, franchise_id: str, playoff_meetings: list[Meeting], seed: int | None) -> tuple[str, bool]:
    """(finish label, in_progress)."""
    if not season.complete and season.final is None:
        return "In progress", True
    if season.champion_id == franchise_id:
        return "Champion", False
    final = season.final
    if final is not None and final.loser is not None and final.loser.franchise_id == franchise_id:
        return "Runner-up", False
    if playoff_meetings:
        return f"Lost {playoff_meetings[-1].round_name or 'playoff game'}", False
    if seed is not None:
        return "Playoffs", False
    return "Missed playoffs", False


def _top_starter(league: League, season: Season, franchise_id: str) -> tuple[str, str, float, float] | None:
    points: dict[str, float] = defaultdict(float)
    vor: dict[str, float] = defaultdict(float)
    for row in league.starts[season.year]:
        if row.franchise_id == franchise_id:
            points[row.player_id] += row.points
            vor[row.player_id] += row.vor
    if not vor:
        return None
    best = max(vor, key=lambda pid: (vor[pid], points[pid]))
    return best, season.player(best).name, round(points[best], 1), round(vor[best], 1)


def season_row(league: League, season: Season, franchise_id: str) -> SeasonRow | None:
    if franchise_id not in season.franchises:
        return None
    games = meetings(league, season, franchise_id)
    regular = [m for m in games if not m.playoff]
    playoff = [m for m in games if m.playoff]
    seed = _seed(season, franchise_id)
    finish, in_progress = _finish(season, franchise_id, playoff, seed)
    standing = next((s for s in season.standings if s.franchise_id == franchise_id), None)
    return SeasonRow(
        year=season.year,
        name=league.name_in(franchise_id, season.year),
        wins=sum(1 for m in regular if m.result == "W"),
        losses=sum(1 for m in regular if m.result == "L"),
        ties=sum(1 for m in regular if m.result == "T"),
        division_record=standing.division_record if standing else "",
        points_for=round(sum(m.own_score for m in regular), 1),
        points_against=round(sum(m.opponent_score for m in regular), 1),
        seed=seed,
        playoff_wins=sum(1 for m in playoff if m.result == "W"),
        playoff_losses=sum(1 for m in playoff if m.result == "L"),
        finish=finish,
        title=season.champion_id == franchise_id,
        in_progress=in_progress,
        top_starter=_top_starter(league, season, franchise_id),
    )


def season_rows(league: League, franchise_id: str) -> list[SeasonRow]:
    """Oldest first."""
    rows = (season_row(league, season, franchise_id) for season in league.seasons)
    return [row for row in rows if row is not None]


def totals(rows: list[SeasonRow] | tuple[SeasonRow, ...]) -> Totals:
    wins, losses, ties = (sum(getattr(r, key) for r in rows) for key in ("wins", "losses", "ties"))
    return Totals(
        games=wins + losses + ties,
        wins=wins,
        losses=losses,
        ties=ties,
        points_for=round(sum(r.points_for for r in rows), 1),
        points_against=round(sum(r.points_against for r in rows), 1),
        playoff_apps=sum(1 for r in rows if r.seed is not None),
        playoff_wins=sum(r.playoff_wins for r in rows),
        playoff_losses=sum(r.playoff_losses for r in rows),
        titles=sum(1 for r in rows if r.title),
    )


def streaks(results: list[str]) -> tuple[str, int, int]:
    """(current streak like W3, longest win streak, longest loss streak) over W/L/T results in order."""
    longest = {"W": 0, "L": 0}
    run_kind, run_length = "", 0
    for result in results:
        if result == run_kind:
            run_length += 1
        else:
            run_kind, run_length = result, 1
        if result in longest:
            longest[result] = max(longest[result], run_length)
    current = f"{run_kind}{run_length}" if run_kind else ""
    return current, longest["W"], longest["L"]


def series(league: League, franchise_id: str, all_meetings: list[Meeting]) -> list[Series]:
    by_opponent: dict[str, list[Meeting]] = defaultdict(list)
    for meeting in all_meetings:
        by_opponent[meeting.opponent_id].append(meeting)
    out: list[Series] = []
    for opponent_id, games in by_opponent.items():

        def split(rows: list[Meeting]) -> tuple[int, int, int]:
            return (
                sum(1 for m in rows if m.result == "W"),
                sum(1 for m in rows if m.result == "L"),
                sum(1 for m in rows if m.result == "T"),
            )

        wins, losses, ties = split(games)
        out.append(
            Series(
                opponent_id=opponent_id,
                opponent_name=league.current_name(opponent_id),
                wins=wins,
                losses=losses,
                ties=ties,
                regular=split([m for m in games if not m.playoff]),
                playoff=split([m for m in games if m.playoff]),
                points_for=round(sum(m.own_score for m in games), 1),
                points_against=round(sum(m.opponent_score for m in games), 1),
                avg_margin=round(sum(m.own_score - m.opponent_score for m in games) / len(games), 1),
                streak=streaks([m.result for m in games])[0],
                last=games[-1],
                meetings=tuple(games),
            )
        )
    return sorted(out, key=lambda s: s.opponent_name.casefold())


def top_starters(league: League, franchise_id: str) -> list[TopStarter]:
    stats: dict[str, dict] = {}
    for row in league.all_starts():
        if row.franchise_id != franchise_id:
            continue
        entry = stats.setdefault(row.player_id, {"first": row.year, "last": row.year, "starts": 0, "points": 0.0, "vor": 0.0})
        entry["first"] = min(entry["first"], row.year)
        entry["last"] = max(entry["last"], row.year)
        entry["starts"] += 1
        entry["points"] += row.points
        entry["vor"] += row.vor
    out = [
        TopStarter(pid, league.player_info(pid).name, league.player_info(pid).position, e["first"], e["last"], e["starts"], round(e["points"], 1), round(e["vor"], 1))
        for pid, e in stats.items()
    ]
    return sorted(out, key=lambda t: (-t.vor, -t.points, t.name))


def franchise_history(league: League, franchise_id: str) -> FranchiseHistory:
    rows = season_rows(league, franchise_id)
    eras: list[EraSummary] = []
    for era in reversed(league.eras(franchise_id)):
        era_rows = tuple(sorted((r for r in rows if era.first_year <= r.year <= era.last_year), key=lambda r: -r.year))
        eras.append(EraSummary(era, era_rows, totals(era_rows)))
    all_meetings = [m for season in league.seasons for m in meetings(league, season, franchise_id)]
    current, longest_win, longest_loss = streaks([m.result for m in all_meetings])
    complete_rows = [r for r in rows if not r.in_progress and (r.wins + r.losses + r.ties)]
    return FranchiseHistory(
        id=franchise_id,
        name=league.current_name(franchise_id),
        eras=tuple(eras),
        totals=totals(rows),
        streak=current,
        longest_win_streak=longest_win,
        longest_loss_streak=longest_loss,
        best_season=max(complete_rows, key=_season_rank, default=None),
        worst_season=min(complete_rows, key=_season_rank, default=None),
        series=tuple(series(league, franchise_id, all_meetings)),
        top_starters=tuple(top_starters(league, franchise_id)),
        playoff_games=tuple(sorted((m for m in all_meetings if m.playoff), key=lambda m: (-m.year, -m.week))),
    )


def _season_rank(row: SeasonRow) -> tuple[float, float]:
    games = row.wins + row.losses + row.ties
    return ((row.wins + 0.5 * row.ties) / games if games else 0.0, row.points_for)


def all_franchises(league: League) -> dict[str, FranchiseHistory]:
    return {fid: franchise_history(league, fid) for fid in league.franchise_ids()}
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/hof/test_hof_franchises.py -v`
Expected: 9 passed.

- [ ] **Step 5: Lint and commit**

Run: `ruff check hof tests/hof`
Expected: no issues.

```bash
git add hof/stats/franchises.py tests/hof/test_hof_franchises.py
git commit -m "feat(hof): franchise histories with eras, streaks, and head-to-head

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Records book

**Files:**
- Create: `hof/stats/records.py`
- Modify: `tests/hof/synthetic.py` (add `four_team_league()`)
- Test: `tests/hof/test_hof_records.py`

- [ ] **Step 1: Add a shared four-team league to `tests/hof/synthetic.py`**

Append to the file (it needs `from hof.stats.league import League` added to its imports):

```python
def four_team_league() -> League:
    """A complete 2020 with a two-round bracket, plus an in-progress 2021 with one game.

    0001 renames from Alpha to Alpha Prime in 2021. 0002's week-1 lineup left 4.0 points on
    the bench; every other lineup was optimal.
    """
    players = {f"a{i}": (f"QB A{i}", "QB") for i in range(1, 5)}
    names_2020 = {"0001": "Alpha", "0002": "Beta", "0003": "Gamma", "0004": "Delta"}
    s2020 = build_season(
        2020,
        players,
        {
            1: [(lineup("0001", {"a1": 20.0}), lineup("0002", {"a2": 10.0}, opt_pts=14.0)), (lineup("0003", {"a3": 15.0}), lineup("0004", {"a4": 5.0}))],
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
        names=names_2020,
    )
    s2021 = build_season(
        2021,
        players,
        {1: [(lineup("0001", {"a1": 10.0}), lineup("0002", {"a2": 5.0}))]},
        last_regular_season_week=2,
        complete=False,
        names={**names_2020, "0001": "Alpha Prime"},
    )
    return League.build([s2020, s2021])
```

- [ ] **Step 2: Write the failing tests**

`tests/hof/test_hof_records.py`:

```python
import pytest
from synthetic import four_team_league

from hof.stats import careers, records
from hof.stats.records import RecordEntry


@pytest.fixture(scope="module")
def book():
    league = four_team_league()
    tables = records.records_book(league, careers.careers(league))
    return {table.key: table for table in tables}


def test_every_spec_table_is_present_in_order():
    league = four_team_league()
    keys = [t.key for t in records.records_book(league, careers.careers(league))]
    assert keys == [
        "team_game_high", "team_game_low", "blowout", "closest", "loss_high", "win_low", "bench_left_game", "final_high",
        "team_season_high", "team_season_low", "record_best", "streak_win", "streak_loss", "bench_left_season", "efficiency_season",
        "player_game_high", "player_game_vor",
        "player_season_high", "player_season_vor", "player_season_starts",
        "career_points", "career_vor", "career_starts", "career_titles",
    ]


def test_team_single_game_records(book):
    assert book["team_game_high"].entries[0] == RecordEntry(30.0, "Alpha", "vs Gamma, 2020 Week 4 (Final)", 2020, 4, True, "0001", None)
    assert len(book["team_game_high"].entries) == 10
    assert book["team_game_low"].lowest_first is True
    assert book["team_game_low"].entries[0].value == 5.0
    assert book["blowout"].entries[0] == RecordEntry(20.0, "Alpha", "over Delta 25.0–5.0, 2020 Week 3 (Semifinal)", 2020, 3, True, "0001", None)
    assert book["closest"].entries[0].value == 2.0 and book["closest"].entries[0].holder == "Delta"
    assert book["loss_high"].entries[0] == RecordEntry(20.0, "Gamma", "lost to Alpha 30.0–20.0, 2020 Week 4 (Final)", 2020, 4, True, "0003", None)
    assert book["win_low"].entries[0] == RecordEntry(10.0, "Alpha Prime", "beat Beta 10.0–5.0, 2021 Week 1", 2021, 1, False, "0001", None)
    assert book["bench_left_game"].entries[0] == RecordEntry(4.0, "Beta", "10.0 of 14.0 possible, 2020 Week 1", 2020, 1, False, "0002", None)
    assert book["final_high"].entries == (RecordEntry(50.0, "Alpha", "30.0–20.0 over Gamma, 2020", 2020, 4, True, "0001", None),)


def test_team_season_records_use_finished_seasons_only(book):
    assert book["team_season_high"].entries[0] == RecordEntry(33.0, "Gamma", "2020, 2-0-0", 2020, None, False, "0003", None)
    assert book["team_season_low"].entries[0].holder == "Delta"
    assert all(entry.year == 2020 for table in ("team_season_high", "team_season_low") for entry in book[table].entries)
    assert book["record_best"].entries[0] == RecordEntry(1.0, "Gamma", "2-0-0, 33.0 pts", 2020, None, False, "0003", None)
    assert book["streak_win"].entries[0] == RecordEntry(3, "Gamma", "2020", 2020, None, False, "0003", None)
    assert book["streak_loss"].entries[0] == RecordEntry(3, "Beta", "2020", 2020, None, False, "0002", None)
    assert book["bench_left_season"].entries[0] == RecordEntry(4.0, "Beta", "2020", 2020, None, False, "0002", None)
    beta = next(e for e in book["efficiency_season"].entries if e.franchise_id == "0002")
    assert beta.value == 0.879
    assert book["efficiency_season"].entries[0].value == 1.0


def test_player_records(book):
    assert book["player_game_high"].entries[0] == RecordEntry(30.0, "QB A1", "Alpha, 2020 Week 4 (Final)", 2020, 4, True, "0001", "a1")
    assert book["player_game_vor"].entries[0] == RecordEntry(20.0, "QB A1", "Alpha, 2020 Week 3 (Semifinal)", 2020, 3, True, "0001", "a1")
    assert book["player_season_high"].entries[0] == RecordEntry(87.0, "QB A1", "Alpha, 2020", 2020, None, False, "0001", "a1")
    assert book["player_season_vor"].entries[0].value == 48.0
    assert book["player_season_starts"].entries[0].value == 4
    assert book["career_points"].entries[0] == RecordEntry(97.0, "QB A1", "2020–2021", 2020, None, False, None, "a1")
    assert book["career_vor"].entries[0].value == 53.0
    assert book["career_starts"].entries[0].value == 5
    assert book["career_titles"].entries[0] == RecordEntry(1, "QB A1", "2020–2021", 2020, None, False, None, "a1")


def test_new_entries_for_a_week(book):
    new = records.entries_from_week(list(book.values()), 2021, 1)
    assert {(table.key, entry.holder) for table, entry in new} >= {("win_low", "Alpha Prime"), ("team_game_low", "Beta")}
    assert all(entry.year == 2021 and entry.week == 1 for _, entry in new)
    assert all(table.group in ("Team, single game", "Player, single game") for table, _ in new)
```

- [ ] **Step 3: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_records.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'hof.stats.records'`.

- [ ] **Step 4: Implement**

`hof/stats/records.py`:

```python
"""The records book: top-ten tables for teams and players, by game, season, and career."""

from __future__ import annotations

from dataclasses import dataclass

from hof.model.season import Game, Season
from hof.stats import franchises
from hof.stats.careers import Career
from hof.stats.league import League

TOP = 10


@dataclass(frozen=True)
class RecordEntry:
    value: float
    holder: str  # franchise name at the time, or player name
    detail: str
    year: int
    week: int | None  # None for season and career records
    playoff: bool
    franchise_id: str | None
    player_id: str | None


@dataclass(frozen=True)
class RecordTable:
    key: str
    title: str
    group: str
    entries: tuple[RecordEntry, ...]  # best first, at most TOP
    lowest_first: bool = False
    unit: str = "pts"


# (key, title, group, lowest_first, unit)
TABLES: tuple[tuple[str, str, str, bool, str], ...] = (
    ("team_game_high", "Most points, game", "Team, single game", False, "pts"),
    ("team_game_low", "Fewest points, game", "Team, single game", True, "pts"),
    ("blowout", "Biggest margin of victory", "Team, single game", False, "pts"),
    ("closest", "Closest game", "Team, single game", True, "pts"),
    ("loss_high", "Most points in a loss", "Team, single game", False, "pts"),
    ("win_low", "Fewest points in a win", "Team, single game", True, "pts"),
    ("bench_left_game", "Most points left on the bench, game", "Team, single game", False, "pts"),
    ("final_high", "Highest-scoring final", "Team, single game", False, "pts"),
    ("team_season_high", "Most points, season", "Team, season", False, "pts"),
    ("team_season_low", "Fewest points, season", "Team, season", True, "pts"),
    ("record_best", "Best record", "Team, season", False, "pct"),
    ("streak_win", "Longest win streak, season", "Team, season", False, "games"),
    ("streak_loss", "Longest loss streak, season", "Team, season", False, "games"),
    ("bench_left_season", "Most points left on the bench, season", "Team, season", False, "pts"),
    ("efficiency_season", "Best lineup efficiency, season", "Team, season", False, "pct"),
    ("player_game_high", "Most points as a starter, game", "Player, single game", False, "pts"),
    ("player_game_vor", "Highest value over replacement, game", "Player, single game", False, "vor"),
    ("player_season_high", "Most points as a starter, season", "Player, season", False, "pts"),
    ("player_season_vor", "Highest value over replacement, season", "Player, season", False, "vor"),
    ("player_season_starts", "Most starts, season", "Player, season", False, "starts"),
    ("career_points", "Most points as a starter, career", "Player, career", False, "pts"),
    ("career_vor", "Highest value over replacement, career", "Player, career", False, "vor"),
    ("career_starts", "Most starts, career", "Player, career", False, "starts"),
    ("career_titles", "Most titles as a starter, career", "Player, career", False, "titles"),
)


def _when(game: Game) -> str:
    label = f"{game.year} Week {game.week}"
    return f"{label} ({game.round_name})" if game.playoff and game.round_name else label


def _score(value: float | None) -> str:
    return f"{value or 0.0:.1f}"


def finished(season: Season) -> bool:
    """Season tables only use seasons whose bracket has been decided."""
    return season.complete or season.final is not None


def _game_entry(value: float, holder: str, detail: str, game: Game, franchise_id: str) -> RecordEntry:
    return RecordEntry(round(value, 1), holder, detail, game.year, game.week, game.playoff, franchise_id, None)


def _season_entry(value: float, holder: str, detail: str, year: int, franchise_id: str) -> RecordEntry:
    return RecordEntry(value, holder, detail, year, None, False, franchise_id, None)


def team_game_entries(league: League) -> dict[str, list[RecordEntry]]:
    out: dict[str, list[RecordEntry]] = {key: [] for key, *_ in TABLES}
    for season in league.seasons:
        for game in season.games():
            for own, opponent in ((game.home, game.away), (game.away, game.home)):
                name = league.name_in(own.franchise_id, season.year)
                other = league.name_in(opponent.franchise_id, season.year)
                score, other_score = own.score or 0.0, opponent.score or 0.0
                fid, when = own.franchise_id, _when(game)
                out["team_game_high"].append(_game_entry(score, name, f"vs {other}, {when}", game, fid))
                out["team_game_low"].append(_game_entry(score, name, f"vs {other}, {when}", game, fid))
                if score > other_score:
                    versus = f"{_score(score)}–{_score(other_score)}"
                    out["blowout"].append(_game_entry(game.margin, name, f"over {other} {versus}, {when}", game, fid))
                    out["closest"].append(_game_entry(game.margin, name, f"over {other} {versus}, {when}", game, fid))
                    out["win_low"].append(_game_entry(score, name, f"beat {other} {versus}, {when}", game, fid))
                elif score < other_score:
                    out["loss_high"].append(_game_entry(score, name, f"lost to {other} {_score(other_score)}–{_score(score)}, {when}", game, fid))
                if own.opt_pts is not None:
                    out["bench_left_game"].append(_game_entry(own.opt_pts - score, name, f"{_score(score)} of {_score(own.opt_pts)} possible, {when}", game, fid))
        final = season.final
        if final is not None and final.winner is not None and final.loser is not None:
            winner, loser = final.winner, final.loser
            out["final_high"].append(
                RecordEntry(
                    round((winner.score or 0.0) + (loser.score or 0.0), 1),
                    league.name_in(winner.franchise_id, season.year),
                    f"{_score(winner.score)}–{_score(loser.score)} over {league.name_in(loser.franchise_id, season.year)}, {season.year}",
                    season.year, final.week, True, winner.franchise_id, None,
                )
            )
    return out


def team_season_entries(league: League) -> dict[str, list[RecordEntry]]:
    out: dict[str, list[RecordEntry]] = {key: [] for key, *_ in TABLES}
    for season in league.seasons:
        if not finished(season):
            continue
        for fid in season.franchises:
            row = franchises.season_row(league, season, fid)
            if row is None or not (row.wins + row.losses + row.ties):
                continue
            games = franchises.meetings(league, season, fid)
            _, longest_win, longest_loss = franchises.streaks([m.result for m in games])
            score = opt = 0.0
            for game in season.games():
                lineup = game.lineup_of(fid)
                if lineup is not None and lineup.opt_pts is not None:
                    score += lineup.score or 0.0
                    opt += lineup.opt_pts

            record = f"{row.wins}-{row.losses}-{row.ties}"
            year = season.year
            out["team_season_high"].append(_season_entry(row.points_for, row.name, f"{year}, {record}", year, fid))
            out["team_season_low"].append(_season_entry(row.points_for, row.name, f"{year}, {record}", year, fid))
            pct = (row.wins + 0.5 * row.ties) / (row.wins + row.losses + row.ties)
            out["record_best"].append(_season_entry(round(pct, 3), row.name, f"{record}, {row.points_for:.1f} pts", year, fid))
            out["streak_win"].append(_season_entry(longest_win, row.name, f"{year}", year, fid))
            out["streak_loss"].append(_season_entry(longest_loss, row.name, f"{year}", year, fid))
            if opt:
                out["bench_left_season"].append(_season_entry(round(opt - score, 1), row.name, f"{year}", year, fid))
                out["efficiency_season"].append(_season_entry(round(score / opt, 3), row.name, f"{year}", year, fid))
    return out


def player_entries(league: League, careers: dict[str, Career]) -> dict[str, list[RecordEntry]]:
    out: dict[str, list[RecordEntry]] = {key: [] for key, *_ in TABLES}
    for season in league.seasons:
        rounds = {g.week: g.round_name for g in season.games() if g.playoff}
        for row in league.starts[season.year]:
            name = league.player_info(row.player_id).name
            franchise = league.name_in(row.franchise_id, season.year)
            when = f"{season.year} Week {row.week}"
            if row.playoff and rounds.get(row.week):
                when += f" ({rounds[row.week]})"
            out["player_game_high"].append(RecordEntry(row.points, name, f"{franchise}, {when}", season.year, row.week, row.playoff, row.franchise_id, row.player_id))
            out["player_game_vor"].append(RecordEntry(row.vor, name, f"{franchise}, {when}", season.year, row.week, row.playoff, row.franchise_id, row.player_id))
    for career in careers.values():
        for line in career.seasons:
            season = league.season(line.year)
            if not finished(season) or not line.starts:
                continue
            franchise = ", ".join(league.name_in(fid, line.year) for fid in line.franchise_ids) or "—"
            main = line.franchise_ids[0] if line.franchise_ids else None
            for key, value in (("player_season_high", line.points), ("player_season_vor", line.vor), ("player_season_starts", line.starts)):
                out[key].append(RecordEntry(value, career.name, f"{franchise}, {line.year}", line.year, None, False, main, career.player_id))
        span = f"{career.first_year}–{career.last_year}"
        for key, value in (("career_points", career.points), ("career_vor", career.vor), ("career_starts", career.starts), ("career_titles", career.titles)):
            out[key].append(RecordEntry(value, career.name, span, career.first_year, None, False, None, career.player_id))
    return out


def records_book(league: League, careers: dict[str, Career]) -> list[RecordTable]:
    pools: dict[str, list[RecordEntry]] = {key: [] for key, *_ in TABLES}
    for source in (team_game_entries(league), team_season_entries(league), player_entries(league, careers)):
        for key, entries in source.items():
            pools[key].extend(entries)
    tables: list[RecordTable] = []
    for key, title, group, lowest_first, unit in TABLES:
        sign = 1 if lowest_first else -1
        ordered = sorted(pools[key], key=lambda e: (sign * e.value, e.year, e.week or 0, e.holder))
        tables.append(RecordTable(key, title, group, tuple(ordered[:TOP]), lowest_first, unit))
    return tables


def entries_from_week(tables: list[RecordTable], year: int, week: int) -> list[tuple[RecordTable, RecordEntry]]:
    """Single-game top-ten entries set in the given week: the recap's "new records"."""
    found = []
    for table in tables:
        if table.group not in ("Team, single game", "Player, single game"):
            continue
        for entry in table.entries:
            if entry.year == year and entry.week == week:
                found.append((table, entry))
    return found
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/hof/test_hof_records.py tests/hof/test_hof_franchises.py -v`
Expected: all pass. If an equality on a `RecordEntry` fails only on the `detail` string, fix the string in the implementation to match the test; the tests define the wording the site and Discord will show.

- [ ] **Step 6: Lint and commit**

Run: `ruff check hof tests/hof`
Expected: no issues.

```bash
git add hof/stats/records.py tests/hof/synthetic.py tests/hof/test_hof_records.py
git commit -m "feat(hof): records book

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Hall of Fame

**Files:**
- Create: `hof/stats/hall.py`
- Test: `tests/hof/test_hof_hall.py`

Induction is evaluated after every *finished* season in order (a season whose final has been played, or that is marked complete), so the season wrap in Plan 4 can announce the class the morning after the final rather than waiting for the February 1 completeness flag. Plaque numbers are full-career figures, not the figures at induction.

- [ ] **Step 1: Write the failing tests**

`tests/hof/test_hof_hall.py`:

```python
from synthetic import four_team_league

from hof.config import HallRules
from hof.stats import careers, franchises, hall
from hof.stats.hall import FranchisePlaque, PlayerPlaque, WatchEntry


def build(rules):
    league = four_team_league()
    return hall.hall_of_fame(league, careers.careers(league), franchises.all_franchises(league), rules)


def test_players_and_franchises_are_inducted_in_the_season_they_cross_the_line():
    result = build(HallRules(player_min_vor=40, player_min_starts=3, franchise_min_titles=1, watch_list_margin=50))
    assert result.players == (
        PlayerPlaque("a1", "QB A1", "QB", 2020, ("Alpha Prime",), 5, 97.0, 53.0, 1),
    )
    assert result.franchises == (FranchisePlaque("0001", "Alpha Prime", 2020, 1, "2-1-0", 0.667),)
    assert result.watch_list == (WatchEntry("a2", "QB A2", "QB", 4, 10.0, 30.0, 0),)
    assert result.rules.player_min_vor == 40


def test_unfinished_seasons_do_not_induct_but_feed_the_watch_list():
    # a1 has 48 value after 2020 and 53 after the in-progress 2021: over 50 only once 2021 counts
    result = build(HallRules(player_min_vor=50, player_min_starts=3, franchise_min_titles=2, watch_list_margin=10))
    assert result.players == ()
    assert result.franchises == ()
    assert result.watch_list == (WatchEntry("a1", "QB A1", "QB", 5, 53.0, 0.0, 0),)


def test_class_years_follow_cumulative_totals():
    league = four_team_league()
    assert hall.player_class_years(league, HallRules(player_min_vor=40, player_min_starts=3)) == {"a1": 2020}
    assert hall.player_class_years(league, HallRules(player_min_vor=10, player_min_starts=1)) == {"a1": 2020, "a3": 2020, "a2": 2020}
    assert hall.franchise_class_years(league, HallRules(franchise_min_titles=1)) == {"0001": 2020}


def test_inactive_players_are_not_on_the_watch_list():
    result = build(HallRules(player_min_vor=40, player_min_starts=3, franchise_min_titles=1, watch_list_margin=500))
    assert [w.player_id for w in result.watch_list] == ["a2"]  # a3 and a4 were not rostered in the newest week
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_hall.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'hof.stats.hall'`.

- [ ] **Step 3: Implement**

`hof/stats/hall.py`:

```python
"""Hall of Fame: rule-based induction evaluated season by season, plus the watch list."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from hof.config import HallRules
from hof.stats.careers import Career
from hof.stats.franchises import FranchiseHistory
from hof.stats.league import League
from hof.stats.records import finished


@dataclass(frozen=True)
class PlayerPlaque:
    player_id: str
    name: str
    position: str
    class_year: int
    franchise_names: tuple[str, ...]  # current names, in order of first stint
    starts: int
    points: float
    vor: float
    titles: int


@dataclass(frozen=True)
class FranchisePlaque:
    franchise_id: str
    name: str
    class_year: int
    titles: int
    record: str
    win_pct: float


@dataclass(frozen=True)
class WatchEntry:
    player_id: str
    name: str
    position: str
    starts: int
    vor: float
    needed_vor: float
    needed_starts: int


@dataclass(frozen=True)
class Hall:
    players: tuple[PlayerPlaque, ...]  # by class year, then value
    franchises: tuple[FranchisePlaque, ...]
    watch_list: tuple[WatchEntry, ...]  # closest to the line first
    rules: HallRules


def player_class_years(league: League, rules: HallRules) -> dict[str, int]:
    """Player id -> the finished season at whose end they crossed both thresholds."""
    starts: dict[str, int] = defaultdict(int)
    vor: dict[str, float] = defaultdict(float)
    inducted: dict[str, int] = {}
    for season in league.seasons:
        if not finished(season):
            continue
        for row in league.starts[season.year]:
            starts[row.player_id] += 1
            vor[row.player_id] += row.vor
        for pid in vor:
            if pid not in inducted and vor[pid] >= rules.player_min_vor and starts[pid] >= rules.player_min_starts:
                inducted[pid] = season.year
    return inducted


def franchise_class_years(league: League, rules: HallRules) -> dict[str, int]:
    """Franchise id -> the season of its qualifying title."""
    titles: dict[str, int] = defaultdict(int)
    inducted: dict[str, int] = {}
    for season in league.seasons:
        champion = season.champion_id
        if champion is None:
            continue
        titles[champion] += 1
        if champion not in inducted and titles[champion] >= rules.franchise_min_titles:
            inducted[champion] = season.year
    return inducted


def hall_of_fame(
    league: League,
    careers: dict[str, Career],
    histories: dict[str, FranchiseHistory],
    rules: HallRules,
) -> Hall:
    player_years = player_class_years(league, rules)
    players = [
        PlayerPlaque(
            player_id=pid,
            name=career.name,
            position=career.position,
            class_year=year,
            franchise_names=tuple(league.current_name(fid) for fid in career.franchise_ids),
            starts=career.starts,
            points=career.points,
            vor=career.vor,
            titles=career.titles,
        )
        for pid, year in player_years.items()
        if (career := careers.get(pid)) is not None
    ]
    franchise_years = franchise_class_years(league, rules)
    plaques = [
        FranchisePlaque(fid, history.name, year, history.totals.titles, history.totals.record, round(history.totals.win_pct, 3))
        for fid, year in franchise_years.items()
        if (history := histories.get(fid)) is not None
    ]
    watch = [
        WatchEntry(
            player_id=career.player_id,
            name=career.name,
            position=career.position,
            starts=career.starts,
            vor=career.vor,
            needed_vor=round(max(0.0, rules.player_min_vor - career.vor), 1),
            needed_starts=max(0, rules.player_min_starts - career.starts),
        )
        for career in careers.values()
        if career.active and career.player_id not in player_years and career.vor >= rules.player_min_vor - rules.watch_list_margin
    ]
    return Hall(
        players=tuple(sorted(players, key=lambda p: (p.class_year, -p.vor, p.name))),
        franchises=tuple(sorted(plaques, key=lambda p: (p.class_year, p.name))),
        watch_list=tuple(sorted(watch, key=lambda w: (w.needed_vor, w.needed_starts, w.name))),
        rules=rules,
    )
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/hof/test_hof_hall.py -v`
Expected: 4 passed.

- [ ] **Step 5: Lint and commit**

Run: `ruff check hof tests/hof`
Expected: no issues.

```bash
git add hof/stats/hall.py tests/hof/test_hof_hall.py
git commit -m "feat(hof): rule-based Hall of Fame with watch list

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Draft hindsight

**Files:**
- Create: `hof/stats/drafts.py`
- Test: `tests/hof/test_hof_drafts.py`

- [ ] **Step 1: Write the failing tests**

`tests/hof/test_hof_drafts.py`:

```python
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
    assert summary.picks[0] == PickLine(2020, 1, 1, "0001", "Alpha", "0001", "a1", "QB A1", "QB", 5, 97.0, 53.0, 97.0, 53.0)
    assert summary.picks[1].original_owner_id == "0002"
    assert summary.picks[3].original_owner_id is None
    assert (summary.picks[1].starts_for, summary.picks[1].vor_for) == (4, 34.0)
    assert summary.steal.player_id == "a2"
    assert summary.bust.player_id == "a3"


def test_rankings_sum_value_by_drafting_franchise():
    league = league_with_draft()
    summaries = drafts.draft_summaries(league, careers.careers(league))
    assert drafts.draft_rankings(league, summaries) == [
        DraftRanking("0001", "Alpha Prime", 1, 53.0),
        DraftRanking("0003", "Gamma", 1, 34.0),
        DraftRanking("0002", "Beta", 1, 10.0),
        DraftRanking("0004", "Delta", 1, 2.0),
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_drafts.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'hof.stats.drafts'`.

- [ ] **Step 3: Implement**

`hof/stats/drafts.py`:

```python
"""Draft hindsight: what every pick produced for the franchise that made it."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from hof.model.season import DraftPick, normalize_name
from hof.stats.careers import Career
from hof.stats.league import League

STARTUP_ROUNDS = 10  # a draft with at least this many rounds is a startup draft, not a rookie draft
TRADED_FROM = "Pick traded from "


@dataclass(frozen=True)
class PickLine:
    year: int
    round: int
    pick: int
    franchise_id: str
    franchise_name: str  # at the time
    original_owner_id: str | None
    player_id: str
    player_name: str
    position: str
    starts_for: int  # as a starter for the drafting franchise, ever
    points_for: float
    vor_for: float
    career_points: float
    career_vor: float


@dataclass(frozen=True)
class DraftSummary:
    year: int
    startup: bool
    rounds: int
    picks: tuple[PickLine, ...]  # draft order
    steal: PickLine | None  # best value outside round one
    bust: PickLine | None  # worst value in round one


@dataclass(frozen=True)
class DraftRanking:
    franchise_id: str
    name: str  # current name
    picks: int
    vor: float


def chain(comments: str) -> list[str]:
    """Franchise names in the pick's 'Pick traded from' lines, oldest first."""
    names: list[str] = []
    for line in comments.strip().strip("[]").splitlines():
        text = line.strip().strip("[]").strip()
        if text.startswith(TRADED_FROM):
            names.append(text[len(TRADED_FROM) :].rstrip(".").strip())
    return names


def original_owner(pick: DraftPick, by_name: dict[str, str]) -> str | None:
    """The franchise the pick originally belonged to; None when the chain names nobody we know."""
    names = chain(pick.comments)
    if not names:
        return pick.franchise_id
    return by_name.get(normalize_name(names[0]))


def value_for(league: League) -> dict[tuple[str, str], tuple[int, float, float]]:
    """(player id, franchise id) -> (starts, points, vor) as a starter for that franchise."""
    totals: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0, 0.0, 0.0])
    for row in league.all_starts():
        entry = totals[(row.player_id, row.franchise_id)]
        entry[0] += 1
        entry[1] += row.points
        entry[2] += row.vor
    return {key: (int(v[0]), round(v[1], 1), round(v[2], 1)) for key, v in totals.items()}


def draft_summaries(league: League, careers: dict[str, Career]) -> list[DraftSummary]:
    by_name = league.franchise_by_name()
    values = value_for(league)
    summaries: list[DraftSummary] = []
    for season in league.seasons:
        if not season.draft:
            continue
        lines: list[PickLine] = []
        for pick in season.draft:
            starts, points, vor = values.get((pick.player_id, pick.franchise_id), (0, 0.0, 0.0))
            career = careers.get(pick.player_id)
            info = league.player_info(pick.player_id)
            lines.append(
                PickLine(
                    year=season.year,
                    round=pick.round,
                    pick=pick.pick,
                    franchise_id=pick.franchise_id,
                    franchise_name=league.name_in(pick.franchise_id, season.year),
                    original_owner_id=original_owner(pick, by_name),
                    player_id=pick.player_id,
                    player_name=info.name,
                    position=info.position,
                    starts_for=starts,
                    points_for=points,
                    vor_for=vor,
                    career_points=career.points if career else 0.0,
                    career_vor=career.vor if career else 0.0,
                )
            )
        rounds = max(line.round for line in lines)
        later = [line for line in lines if line.round > 1]
        first = [line for line in lines if line.round == 1]
        summaries.append(
            DraftSummary(
                year=season.year,
                startup=rounds >= STARTUP_ROUNDS,
                rounds=rounds,
                picks=tuple(lines),
                steal=max(later, key=lambda line: (line.vor_for, -line.round, -line.pick), default=None),
                bust=min(first, key=lambda line: (line.vor_for, line.pick), default=None),
            )
        )
    return summaries


def draft_rankings(league: League, summaries: list[DraftSummary]) -> list[DraftRanking]:
    picks: dict[str, int] = defaultdict(int)
    vor: dict[str, float] = defaultdict(float)
    for summary in summaries:
        for line in summary.picks:
            picks[line.franchise_id] += 1
            vor[line.franchise_id] += line.vor_for
    rankings = [DraftRanking(fid, league.current_name(fid), picks[fid], round(vor[fid], 1)) for fid in picks]
    return sorted(rankings, key=lambda r: (-r.vor, r.name))
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/hof/test_hof_drafts.py -v`
Expected: 5 passed.

- [ ] **Step 5: Lint and commit**

Run: `ruff check hof tests/hof`
Expected: no issues.

```bash
git add hof/stats/drafts.py tests/hof/test_hof_drafts.py
git commit -m "feat(hof): draft hindsight with original owners from pick comments

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Trade ledger

**Files:**
- Create: `hof/stats/trades.py`
- Test: `tests/hof/test_hof_trades.py`

- [ ] **Step 1: Write the failing tests**

`tests/hof/test_hof_trades.py`:

```python
from synthetic import build_season, lineup

from hof.model.season import BracketGame, DraftPick
from hof.model.transactions import Trade, TransactionLog
from hof.stats import careers, trades
from hof.stats.league import League
from hof.stats.trades import Asset, TradeSide

PLAYERS = {
    "q1": ("QB One", "QB"),
    "q2": ("QB Two", "QB"),
    "r1": ("RB One", "RB"),
    "r2": ("RB Two", "RB"),
    "rk2": ("Rookie Two", "RB"),
}
NAMES = {"0001": "Alpha", "0002": "Beta"}


def trade_league():
    """Four trades: a player for dollars (A), a future pick for a current-year pick (B), an
    offseason player swap that lands in the next season (C), and a pending one (D)."""
    log_2020 = TransactionLog(
        trades=(
            Trade(150, "0001", "0002", ("r1",), ("BB_5",), "cash grab"),
            Trade(160, "0002", "0001", ("FP_0002_2021_1",), ("DP_1_1",), ""),
            Trade(999, "0001", "0002", ("q1",), ("q2",), ""),
        ),
        waivers=(),
        free_agents=(),
        roster_moves=(),
        lock_times=(100, 200, 300),
    )
    s2020 = build_season(
        2020,
        PLAYERS,
        {
            1: [(lineup("0001", {"q1": 20.0, "r1": 10.0}), lineup("0002", {"q2": 15.0, "r2": 8.0}))],
            2: [(lineup("0002", {"q2": 12.0, "r1": 14.0, "r2": 3.0}), lineup("0001", {"q1": 9.0}))],
            3: [(lineup("0001", {"q1": 30.0}), lineup("0002", {"q2": 5.0, "r1": 7.0, "r2": 2.0}))],
        },
        last_regular_season_week=2,
        franchises=("0001", "0002"),
        bracket=(BracketGame(3, "1", 0, "0001", "0002", 1, 2),),
        transactions=log_2020,
        draft=(DraftPick(2, 2, "0002", "r2", 40),),
        names=NAMES,
    )
    log_2021 = TransactionLog(
        trades=(Trade(50, "0001", "0002", ("rk2",), ("q1",), ""),),
        waivers=(),
        free_agents=(),
        roster_moves=(),
        lock_times=(),
    )
    s2021 = build_season(
        2021,
        PLAYERS,
        {1: [(lineup("0002", {"q1": 20.0}), lineup("0001", {"q2": 5.0, "rk2": 9.0}))]},
        last_regular_season_week=2,
        franchises=("0001", "0002"),
        complete=False,
        transactions=log_2021,
        draft=(DraftPick(1, 1, "0001", "rk2", 60, "[Pick traded from Beta.]"),),
        names=NAMES,
    )
    return League.build([s2020, s2021])


def ledger():
    league = trade_league()
    return trades.trade_ledger(league, careers.stints(league))


def test_ledger_is_newest_first_with_effective_weeks():
    lines = ledger()
    assert [(line.year, line.timestamp) for line in lines] == [(2021, 50), (2020, 999), (2020, 160), (2020, 150)]
    assert [line.effective for line in lines] == [(2022, 0), (2021, 0), (2020, 2), (2020, 2)]
    assert [line.pending for line in lines] == [True, False, False, False]


def test_player_for_dollars_is_credited_by_stint_from_the_effective_week():
    line = ledger()[3]
    assert line.comments == "cash grab"
    assert line.sides == (
        TradeSide("0001", "Alpha", (Asset("BB_5", "dollars", "$5 blind-bid dollars", None, 0, 0.0, 0.0),), 0.0),
        TradeSide("0002", "Beta", (Asset("r1", "player", "RB One (RB)", "r1", 2, 21.0, 16.0),), 16.0),
    )
    assert line.verdict == "Ahead: Beta by 16.0"


def test_picks_resolve_to_players_and_credit_the_drafting_franchise():
    line = ledger()[2]
    beta, alpha = line.sides  # franchise1 of this trade is Beta, so it is listed first
    assert (beta.franchise_id, alpha.franchise_id) == ("0002", "0001")
    assert alpha.received == (Asset("FP_0002_2021_1", "future_pick", "Beta 2021 Round 1 pick → Rookie Two", "rk2", 1, 9.0, 0.0),)
    assert beta.received == (Asset("DP_1_1", "pick", "2020 Round 2 Pick 2 → RB Two", "r2", 3, 13.0, 0.0),)
    assert line.verdict == "Even"


def test_offseason_trade_lands_in_the_next_season():
    line = ledger()[1]
    alpha, beta = line.sides
    assert beta.received[0] == Asset("q1", "player", "QB One (QB)", "q1", 1, 20.0, 15.0)
    assert alpha.received[0] == Asset("q2", "player", "QB Two (QB)", "q2", 1, 5.0, 0.0)
    assert line.verdict == "Ahead: Beta by 15.0"


def test_pending_trade_has_no_values():
    line = ledger()[0]
    assert line.verdict == "Pending"
    assert all(asset.starts == 0 and asset.vor == 0.0 for side in line.sides for asset in side.received)
    assert line.sides[1].received[0].label == "Rookie Two (RB)"


def test_unresolvable_picks_keep_their_label():
    league = trade_league()
    by_name = league.franchise_by_name()
    assert trades.resolve_future_pick("FP_0002_2027_1", league, by_name) is None
    assert trades.resolve_future_pick("FP_0009_2021_1", league, by_name) is None
    assert trades.resolve_future_pick("FP_bad", league, by_name) is None
    assert trades.resolve_current_pick("DP_5_5", league.season(2020)) is None
    assert trades.resolve_current_pick("DP_x_y", league.season(2020)) is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_trades.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'hof.stats.trades'`.

- [ ] **Step 3: Implement**

`hof/stats/trades.py`:

```python
"""The trade ledger: what each side received and what it went on to produce as starters."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from bdfl.assets import format_dollars
from hof.model.season import DraftPick, Season
from hof.stats.careers import Stint, WeekKey, effective_key
from hof.stats.drafts import original_owner
from hof.stats.league import League
from hof.stats.vor import Start


@dataclass(frozen=True)
class Asset:
    code: str
    kind: str  # player, pick, future_pick, dollars
    label: str
    player_id: str | None  # the player, or the player a pick became
    starts: int  # as a starter for the receiving franchise since the trade
    points: float
    vor: float


@dataclass(frozen=True)
class TradeSide:
    franchise_id: str
    name: str  # at the time
    received: tuple[Asset, ...]
    vor: float


@dataclass(frozen=True)
class TradeLine:
    year: int
    timestamp: int
    effective: WeekKey
    pending: bool  # takes effect after the newest rostered week, so nothing has been produced yet
    sides: tuple[TradeSide, TradeSide]
    comments: str
    verdict: str


StartIndex = dict[tuple[str, str], list[Start]]  # (player id, franchise id) -> starts


def resolve_future_pick(code: str, league: League, by_name: dict[str, str]) -> tuple[DraftPick, int] | None:
    """FP_<franchise>_<year>_<round> -> (the pick it became, draft year), when exactly one pick matches."""
    parts = code.split("_")
    if len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit():
        return None
    owner, year, round_ = parts[1], int(parts[2]), int(parts[3])
    try:
        season = league.season(year)
    except KeyError:
        return None
    matches = [p for p in season.draft if p.round == round_ and original_owner(p, by_name) == owner]
    return (matches[0], year) if len(matches) == 1 else None


def resolve_current_pick(code: str, season: Season) -> DraftPick | None:
    """DP_<round>_<pick>, both zero-based, -> that pick in the season's draft."""
    parts = code.split("_")
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        return None
    round_, pick = int(parts[1]) + 1, int(parts[2]) + 1
    return next((p for p in season.draft if p.round == round_ and p.pick == pick), None)


def produced(index: StartIndex, stints: list[Stint], player_id: str, franchise_id: str, since: WeekKey) -> tuple[int, float, float]:
    """(starts, points, vor) for the franchise during the player's first stint that reaches `since`."""
    stint = next((s for s in stints if s.franchise_id == franchise_id and s.end >= since), None)
    if stint is None:
        return 0, 0.0, 0.0
    start = max(stint.start, since)
    rows = [r for r in index.get((player_id, franchise_id), []) if start <= (r.year, r.week) <= stint.end]
    return len(rows), round(sum(r.points for r in rows), 1), round(sum(r.vor for r in rows), 1)


def _player_label(league: League, player_id: str) -> str:
    info = league.player_info(player_id)
    return f"{info.name} ({info.position})"


def asset(
    code: str,
    season: Season,
    league: League,
    by_name: dict[str, str],
    index: StartIndex,
    all_stints: dict[str, list[Stint]],
    receiver: str,
    since: WeekKey,
    pending: bool,
) -> Asset:
    def valued(kind: str, label: str, player_id: str | None, from_key: WeekKey) -> Asset:
        if player_id is None or pending:
            return Asset(code, kind, label, player_id, 0, 0.0, 0.0)
        starts, points, vor = produced(index, all_stints.get(player_id, []), player_id, receiver, from_key)
        return Asset(code, kind, label, player_id, starts, points, vor)

    if code.isalnum():
        return valued("player", _player_label(league, code), code, since)
    parts = code.split("_")
    if parts[0] == "BB" and len(parts) == 2:
        return Asset(code, "dollars", f"{format_dollars(parts[1])} blind-bid dollars", None, 0, 0.0, 0.0)
    if parts[0] == "FP" and len(parts) == 4:
        label = f"{league.name_in(parts[1], season.year)} {parts[2]} Round {parts[3]} pick"
        resolved = resolve_future_pick(code, league, by_name)
        if resolved is None:
            return Asset(code, "future_pick", label, None, 0, 0.0, 0.0)
        pick, year = resolved
        return valued("future_pick", f"{label} → {league.player_info(pick.player_id).name}", pick.player_id, (year, 0))
    if parts[0] == "DP" and len(parts) == 3:
        pick = resolve_current_pick(code, season)
        label = f"{season.year} Round {parts[1]} Pick {parts[2]}"
        if pick is not None:
            label = f"{season.year} Round {pick.round} Pick {pick.pick} → {league.player_info(pick.player_id).name}"
            return valued("pick", label, pick.player_id, (season.year, 0))
        return Asset(code, "pick", label, None, 0, 0.0, 0.0)
    return Asset(code, "other", code, None, 0, 0.0, 0.0)


def verdict(first: TradeSide, second: TradeSide, pending: bool) -> str:
    if pending:
        return "Pending"
    diff = round(first.vor - second.vor, 1)
    if abs(diff) < 0.05:
        return "Even"
    ahead = first if diff > 0 else second
    return f"Ahead: {ahead.name} by {abs(diff):.1f}"


def trade_ledger(league: League, all_stints: dict[str, list[Stint]]) -> list[TradeLine]:
    """Every trade in every season, newest first."""
    by_name = league.franchise_by_name()
    index: StartIndex = defaultdict(list)
    for row in league.all_starts():
        index[(row.player_id, row.franchise_id)].append(row)
    newest = league.latest_rostered_week() or (0, 0)
    lines: list[TradeLine] = []
    for season in league.seasons:
        for trade in season.transactions.trades:
            since = effective_key(season, trade.timestamp)
            pending = since > newest
            sides = []
            for receiver, codes in ((trade.franchise1, trade.gave_up2), (trade.franchise2, trade.gave_up1)):
                received = tuple(asset(code, season, league, by_name, index, all_stints, receiver, since, pending) for code in codes)
                sides.append(TradeSide(receiver, league.name_in(receiver, season.year), received, round(sum(a.vor for a in received), 1)))
            first, second = sides
            lines.append(TradeLine(season.year, trade.timestamp, since, pending, (first, second), trade.comments, verdict(first, second, pending)))
    return sorted(lines, key=lambda line: (-line.year, -line.timestamp))
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/hof/test_hof_trades.py -v`
Expected: 6 passed. The value expectations come from the two-franchise baselines: with two teams the QB baseline is the lower QB each week and the RB baseline the lowest RB started, so RB One's week 2 and 3 starts for Beta are worth 11.0 and 5.0.

- [ ] **Step 5: Lint and commit**

Run: `ruff check hof tests/hof`
Expected: no issues.

```bash
git add hof/stats/trades.py tests/hof/test_hof_trades.py
git commit -m "feat(hof): trade ledger with pick resolution and stint attribution

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Weekly recap facts

**Files:**
- Create: `hof/stats/milestones.py`
- Test: `tests/hof/test_hof_milestones.py`

Everything the Tuesday recap says, computed for one completed week, plus the season awards the wrap needs. Plan 4 turns `RecapFacts` and `SeasonAwards` into embeds; this task only produces the facts.

- [ ] **Step 1: Write the failing tests**

`tests/hof/test_hof_milestones.py`:

```python
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_milestones.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'hof.stats.milestones'`.

- [ ] **Step 3: Implement**

`hof/stats/milestones.py`:

```python
"""Facts for the weekly recap: the week's best, new records, milestones, series firsts, standings."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from hof.model.season import Season
from hof.stats import franchises
from hof.stats.careers import WeekKey
from hof.stats.league import League
from hof.stats.records import RecordTable, entries_from_week

PLAYOFF_SPOTS = 6
POINT_STEP = 500
START_STEP = 100
SERIES_GAP_SEASONS = 2


@dataclass(frozen=True)
class RecapFacts:
    year: int
    week: int
    playoff: bool
    high_score: tuple[str, float] | None  # (franchise name, score)
    top_starter: tuple[str, str, float, float] | None  # (player, franchise, points, vor)
    new_records: tuple[str, ...]
    milestones: tuple[str, ...]
    series_firsts: tuple[str, ...]
    playoff_picture: tuple[str, ...]  # regular-season weeks only
    bracket: tuple[str, ...]  # playoff weeks only


@dataclass(frozen=True)
class SeasonAwards:
    """The season wrap's numbers; every field is None when the season has no counted games."""

    year: int
    top_scorer: tuple[str, str, float] | None  # (player, franchise, points)
    best_vor: tuple[str, str, float] | None  # (player, franchise, vor)
    best_manager: tuple[str, float] | None  # (franchise, lineup efficiency)
    most_bench_left: tuple[str, float] | None  # (franchise, points left on the bench)
    champion: tuple[str, str, float, int | None] | None  # (name, record, points for, all-time rank of that season's points)


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _format(value: float, unit: str) -> str:
    if unit in ("starts", "games", "titles"):
        return f"{int(value)} {unit}"
    if unit == "pct":
        return f"{value:.3f}"
    return f"{value:.1f} {unit}"


def new_records(tables: list[RecordTable], year: int, week: int) -> tuple[str, ...]:
    lines = []
    for table, entry in entries_from_week(tables, year, week):
        rank = table.entries.index(entry) + 1
        lines.append(f"{entry.holder} — {_format(entry.value, table.unit)} ({table.title}, #{rank})")
    return tuple(lines)


def week_milestones(league: League, key: WeekKey, point_step: int, start_step: int) -> tuple[str, ...]:
    points: dict[str, float] = defaultdict(float)
    starts: dict[str, int] = defaultdict(int)
    lines: list[str] = []
    for row in league.all_starts():
        if (row.year, row.week) >= key:
            continue
        points[row.player_id] += row.points
        starts[row.player_id] += 1
    this_week = [r for r in league.starts.get(key[0], []) if r.week == key[1]]
    for row in sorted(this_week, key=lambda r: (league.player_info(r.player_id).name, r.player_id)):
        name = league.player_info(row.player_id).name
        franchise = league.name_in(row.franchise_id, row.year)
        before_points, after_points = points[row.player_id], points[row.player_id] + row.points
        if int(before_points // point_step) < int(after_points // point_step):
            lines.append(f"{name} passed {int(after_points // point_step) * point_step} career points as a starter ({franchise})")
        after_starts = starts[row.player_id] + 1
        if after_starts % start_step == 0:
            lines.append(f"{name} made career start number {after_starts} ({franchise})")
    return tuple(lines)


def series_firsts(league: League, season: Season, week: int) -> tuple[str, ...]:
    lines: list[str] = []
    for game in season.games():
        if game.week != week or game.winner is None or game.loser is None:
            continue
        winner, loser = game.winner.franchise_id, game.loser.franchise_id
        previous = [
            m
            for s in league.seasons
            if s.year <= season.year
            for m in franchises.meetings(league, s, winner)
            if m.opponent_id == loser and (s.year, m.week) < (season.year, week)
        ]
        wins = [m for m in previous if m.result == "W"]
        record = franchises.series(league, winner, previous + [m for m in franchises.meetings(league, season, winner) if m.opponent_id == loser and m.week == week])[0]
        series_text = f"series now {record.wins}-{record.losses}-{record.ties}"
        winner_name, loser_name = league.name_in(winner, season.year), league.name_in(loser, season.year)
        if not wins:
            lines.append(f"{winner_name} beat {loser_name} for the first time ever ({series_text})")
        elif wins[-1].year <= season.year - SERIES_GAP_SEASONS:
            lines.append(f"{winner_name} beat {loser_name} for the first time since {wins[-1].year} ({series_text})")
    return tuple(lines)


def playoff_picture(league: League, season: Season) -> tuple[str, ...]:
    rows = [row for fid in season.franchises if (row := franchises.season_row(league, season, fid)) is not None]
    if season.standings:
        order = {s.franchise_id: i for i, s in enumerate(season.standings)}
        ids = {league.name_in(fid, season.year): fid for fid in season.franchises}
        rows.sort(key=lambda r: order.get(ids.get(r.name, ""), 99))
    else:
        rows.sort(key=lambda r: (-(r.wins + 0.5 * r.ties), -r.points_for, r.name))
    lines = [f"{i}. {row.name} {row.wins}-{row.losses}-{row.ties}" for i, row in enumerate(rows[:PLAYOFF_SPOTS], start=1)]
    if len(rows) > PLAYOFF_SPOTS:
        sixth = rows[PLAYOFF_SPOTS - 1]
        close = [f"{row.name} ({row.wins}-{row.losses}-{row.ties})" for row in rows[PLAYOFF_SPOTS:] if row.wins >= sixth.wins - 1]
        if close:
            lines.append("Within a game: " + ", ".join(close))
    return tuple(lines)


def bracket_summary(league: League, season: Season, week: int) -> tuple[str, ...]:
    lines: list[str] = []
    for game in season.games():
        if game.week != week or not game.playoff:
            continue
        winner, loser = game.winner or game.home, game.loser or game.away
        lines.append(
            f"{game.round_name}: {league.name_in(winner.franchise_id, season.year)} {winner.score or 0.0:.1f}, "
            f"{league.name_in(loser.franchise_id, season.year)} {loser.score or 0.0:.1f}"
        )
    upcoming = [g for g in season.bracket if g.week > week]
    if upcoming:
        next_week = min(g.week for g in upcoming)
        for game in upcoming:
            if game.week == next_week and game.home_id and game.away_id:
                lines.append(f"Next: {season.round_name(game.round_index)}, {league.name_in(game.home_id, season.year)} vs {league.name_in(game.away_id, season.year)}")
    return tuple(lines)


def season_awards(league: League, tables: list[RecordTable], year: int) -> SeasonAwards:
    season = league.season(year)
    points: dict[str, float] = defaultdict(float)
    vor: dict[str, float] = defaultdict(float)
    franchise_of: dict[str, str] = {}
    for row in league.starts.get(year, []):
        points[row.player_id] += row.points
        vor[row.player_id] += row.vor
        franchise_of[row.player_id] = row.franchise_id

    def player_award(totals: dict[str, float]) -> tuple[str, str, float] | None:
        if not totals:
            return None
        best = max(totals, key=lambda pid: (totals[pid], league.player_info(pid).name))
        return league.player_info(best).name, league.name_in(franchise_of[best], year), round(totals[best], 1)

    scored: dict[str, float] = defaultdict(float)
    optimal: dict[str, float] = defaultdict(float)
    for game in season.games():
        for lineup in (game.home, game.away):
            if lineup.opt_pts is not None:
                scored[lineup.franchise_id] += lineup.score or 0.0
                optimal[lineup.franchise_id] += lineup.opt_pts
    manager = bench = None
    if optimal:
        best = max(optimal, key=lambda fid: (scored[fid] / optimal[fid], scored[fid]))
        manager = (league.name_in(best, year), round(scored[best] / optimal[best], 3))
        most = max(optimal, key=lambda fid: (optimal[fid] - scored[fid], fid))
        bench = (league.name_in(most, year), round(optimal[most] - scored[most], 1))
    champion = None
    if season.champion_id is not None:
        row = franchises.season_row(league, season, season.champion_id)
        if row is not None:
            table = next(t for t in tables if t.key == "team_season_high")
            rank = next((i + 1 for i, e in enumerate(table.entries) if e.year == year and e.franchise_id == season.champion_id), None)
            champion = (row.name, f"{row.wins}-{row.losses}-{row.ties}", row.points_for, rank)
    return SeasonAwards(year, player_award(points), player_award(vor), manager, bench, champion)


def recap_facts(
    league: League,
    tables: list[RecordTable],
    key: WeekKey,
    point_step: int = POINT_STEP,
    start_step: int = START_STEP,
) -> RecapFacts:
    year, week = key
    season = league.season(year)
    games = [g for g in season.games() if g.week == week]
    playoff = week > season.last_regular_season_week
    high: tuple[str, float] | None = None
    for game in games:
        for lineup in (game.home, game.away):
            if high is None or (lineup.score or 0.0) > high[1]:
                high = (league.name_in(lineup.franchise_id, year), lineup.score or 0.0)
    top: tuple[str, str, float, float] | None = None
    for row in league.starts.get(year, []):
        if row.week == week and (top is None or (row.vor, row.points) > (top[3], top[2])):
            top = (league.player_info(row.player_id).name, league.name_in(row.franchise_id, year), row.points, row.vor)
    return RecapFacts(
        year=year,
        week=week,
        playoff=playoff,
        high_score=high,
        top_starter=top,
        new_records=new_records(tables, year, week),
        milestones=week_milestones(league, key, point_step, start_step),
        series_firsts=series_firsts(league, season, week),
        playoff_picture=() if playoff else playoff_picture(league, season),
        bracket=bracket_summary(league, season, week) if playoff else (),
    )
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/hof/test_hof_milestones.py -v`
Expected: 8 passed.

- [ ] **Step 5: Lint and commit**

Run: `ruff check hof tests/hof`
Expected: no issues.

```bash
git add hof/stats/milestones.py tests/hof/test_hof_milestones.py
git commit -m "feat(hof): weekly recap facts

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: `compute()`, the `stats` command, and calibration

**Files:**
- Create: `hof/stats/model.py`
- Modify: `hof/__main__.py`, `README.md`
- Test: `tests/hof/test_hof_model.py`

- [ ] **Step 1: Write the failing tests**

`tests/hof/test_hof_model.py`:

```python
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_model.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'hof.stats.model'`.

- [ ] **Step 3: Implement**

`hof/stats/model.py`:

```python
"""One call that computes everything the site and the Discord posts render."""

from __future__ import annotations

from dataclasses import dataclass

from hof.config import HallRules
from hof.model.season import Season
from hof.stats import careers as careers_mod
from hof.stats import drafts as drafts_mod
from hof.stats import franchises as franchises_mod
from hof.stats import hall as hall_mod
from hof.stats import records as records_mod
from hof.stats import trades as trades_mod
from hof.stats.careers import Career, WeekKey
from hof.stats.drafts import DraftRanking, DraftSummary
from hof.stats.franchises import FranchiseHistory
from hof.stats.hall import Hall
from hof.stats.league import League
from hof.stats.records import RecordTable
from hof.stats.trades import TradeLine


@dataclass
class Model:
    league: League
    careers: dict[str, Career]
    histories: dict[str, FranchiseHistory]
    records: list[RecordTable]
    hall: Hall
    drafts: list[DraftSummary]
    draft_rankings: list[DraftRanking]
    trades: list[TradeLine]
    through: WeekKey | None  # newest (year, week) with a counted game
    champions: list[tuple[int, str, str]]  # (year, champion id, runner-up id), oldest first


def latest_played_week(league: League) -> WeekKey | None:
    for season in reversed(league.seasons):
        games = season.games()
        if games:
            return season.year, max(g.week for g in games)
    return None


def champions(league: League) -> list[tuple[int, str, str]]:
    out = []
    for season in league.seasons:
        final = season.final
        if final is not None and final.winner is not None and final.loser is not None:
            out.append((season.year, final.winner.franchise_id, final.loser.franchise_id))
    return out


def compute(seasons: list[Season], rules: HallRules) -> Model:
    league = League.build(seasons)
    careers = careers_mod.careers(league)
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
        trades=trades_mod.trade_ledger(league, careers_mod.stints(league)),
        through=latest_played_week(league),
        champions=champions(league),
    )
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/hof/test_hof_model.py -v`
Expected: 2 passed. The fixture test runs the whole pipeline on real data; a failure there is a real bug in an earlier task, so fix it at the source rather than loosening the assertion.

- [ ] **Step 5: Add the `stats` command**

In `hof/__main__.py`, add the imports:

```python
from hof.snapshots import load_all
from hof.stats.model import compute
```

add a subparser after the `fetch` one:

```python
    commands.add_parser("stats", help="compute everything and print a calibration report")
```

and handle it after the `fetch` branch, before `return 2`:

```python
    if args.command == "stats":
        model = compute(load_all(args.data), config.hall)
        print_report(model, config.hall)
        return 0
```

Add the report function above `main`:

```python
def print_report(model, rules) -> None:
    """A calibration report: what the Hall of Fame looks like under the config thresholds and nearby ones."""
    league = model.league
    print(f"seasons: {league.seasons[0].year}–{league.seasons[-1].year}, through {model.through}")
    print("champions:", ", ".join(f"{y} {league.current_name(c)}" for y, c, _ in model.champions))
    print(f"\nHall of Fame at vor>={rules.player_min_vor:g}, starts>={rules.player_min_starts}: {len(model.hall.players)} players")
    for plaque in model.hall.players:
        print(f"  {plaque.class_year}  {plaque.name:<24} {plaque.position:<3} GS={plaque.starts:<4} pts={plaque.points:8.1f} vor={plaque.vor:7.1f} titles={plaque.titles}")
    print("\nplayers clearing each threshold (with the configured minimum starts):")
    careers = [c for c in model.careers.values() if c.starts >= rules.player_min_starts]
    for threshold in (250, 300, 400, 500, 600, 800):
        print(f"  vor>={threshold}: {sum(1 for c in careers if c.vor >= threshold)}")
    print(f"\nfranchise plaques at {rules.franchise_min_titles} titles: " + ", ".join(f"{p.name} ({p.titles})" for p in model.hall.franchises))
    print("\nwatch list:")
    for entry in model.hall.watch_list[:10]:
        print(f"  {entry.name:<24} vor={entry.vor:7.1f} needs {entry.needed_vor:g} more, starts={entry.starts}")
    print("\nrecords book, top entry per table:")
    for table in model.records:
        if table.entries:
            top = table.entries[0]
            print(f"  {table.title:<45} {top.holder:<28} {top.value:>8} {top.detail}")
    print(f"\ntrades: {len(model.trades)} ({sum(1 for t in model.trades if t.pending)} pending)")
    print("drafts:", ", ".join(f"{d.year} ({d.rounds} rounds{', startup' if d.startup else ''})" for d in model.drafts))
```

Update the module docstring to `{fetch,stats}` and add a CLI test to `tests/hof/test_hof_cli.py`:

```python
def test_stats_command_prints_a_report(tmp_path, fixtures_dir, capsys):
    code = cli.main(["--data", str(fixtures_dir), "--config", str(CONFIG), "stats"])
    assert code == 0
    out = capsys.readouterr().out
    assert "champions: 2020 Marcus Peters' Peter Peckers" in out
    assert "Hall of Fame at vor>=400" in out
    assert "records book, top entry per table:" in out
```

Run: `pytest tests/hof/test_hof_cli.py -v`
Expected: 3 passed.

- [ ] **Step 6: Run the report on the real backfill and read it**

```bash
python -m hof stats 2>&1 | tee /tmp/hof-stats.txt | head -80
```

Expected: it finishes in under a minute with no `WARNING` lines about dropped bracket games, eleven champions matching the list at the top of this plan, and the threshold counts close to 63 at 400 and 34 at 600. Read the top-entry lines for the records book: every holder should be a franchise or player name (never an id), and no value should look impossible (a single-game team score above 250 or below 30 means a lineup parsed wrong). Paste the threshold block into the commit message of the next step so the owner can pick thresholds without rerunning it.

If a `WARNING` about an unresolvable transaction or a missing player appears, note it in the commit message; those are data quirks for Plan 3 to render gracefully, not blockers.

- [ ] **Step 7: Document and commit**

In `README.md`, in the "Hall of Records (in progress)" section, add after the fetch commands:

```bash
python -m hof stats            # compute every stat and print the Hall of Fame calibration report
```

```bash
git add hof/stats/model.py hof/__main__.py tests/hof/test_hof_model.py tests/hof/test_hof_cli.py README.md
git commit -m "feat(hof): compute() and the stats calibration report

<paste the threshold block from python -m hof stats here>

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 8: Full suite and lint**

Run: `ruff check src tests scripts hof && pytest`
Expected: no lint issues; every test passes.

---

## After this plan

- The owner reads the calibration report and sets `player_min_vor` (and possibly `player_min_starts`) in `data/config.toml`. Nothing else in the pipeline depends on the choice, so it can be changed any time before or after Plan 3 ships.
- Plan 3 renders `Model` into the site and adds the workflow. Plan 4 turns `RecapFacts`, `SeasonAwards`, and the Hall of Fame class into Discord embeds and adds `notify`.

## Amendments after review (2026-09-07)

Three changes landed on top of the executed plan, all in `hof/stats/`:

1. `careers.effective_key`: a season with no lock times yet (the whole offseason and the days before week 1) puts every transaction in week 1 of that season, not in the next season. Before this, the 19 trades of the 2026 offseason showed as effective in 2027 and "Pending" for the wrong reason, and their arrivals could not be matched.
2. `careers.bridge_gaps` and `careers.roster_stints`: MFL's weekly lineups omit players on injured reserve and the taxi squad, so a stint is no longer broken by a gap unless a drop or a trade away falls inside it. On the real backfill this removed 534 spurious stints (2,582 to 2,048) and every false "joined" arrival. `careers()` accepts the bridged stints so `compute()` builds them once and shares them with the trade ledger.
3. `trades.trade_ledger`: a trade is pending until a *played* week reaches its effective week. MFL lists week 1 lineups before kickoff, so "newest rostered week" was already 2026 week 1 and marked those trades settled with an "Even" verdict.
