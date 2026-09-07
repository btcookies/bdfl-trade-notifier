# Hall of Records, Plan 1 of 4: Data Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fetch every BDFL season from MFL into versioned JSON snapshots, load them into typed season objects, and compute per-start value over replacement, ending with the full 2016 to 2026 backfill committed to the repo.

**Architecture:** A new top-level `hof` package beside the notifier's `src/bdfl`. `hof.fetch` writes raw MFL export bodies under `data/raw/<year>/`, `hof.snapshots` loads them into `hof.model` dataclasses, and `hof.stats.vor` turns counted games into `Start` rows. Nothing here renders HTML or posts to Discord; those are plans 3 and 4.

**Tech Stack:** Python 3.13, `requests` through the existing `bdfl.mfl.MflClient`, `tomllib`, pytest with `responses` for HTTP stubs, ruff.

**Spec:** `docs/superpowers/specs/2026-09-06-hall-of-records-design.md`, sections 3 to 6, 10 to 12.

---

## Why four plans

The spec is one service but four separable deliverables, each testable on its own:

1. **This plan.** Snapshots, model, VOR, backfill. Ends with `data/raw/` populated and loadable.
2. **Stats.** Careers, franchises and eras, head-to-head, records book, Hall of Fame, drafts, trades, weekly milestones. Pure functions over `Season` and `Start`.
3. **Site and workflow.** Templates, `build`, static assets, the GitHub Actions workflow with Pages deploy.
4. **Discord.** Recap and wrap embeds, `notify`, the state file, the workflow's notify step.

Plans 2 to 4 are written after the previous one ships, against the real code. Their task outlines are at the end of this document so the shape of the whole is visible.

## Conventions for this repo

- Run everything from the repo root with the virtualenv active: `source .venv/bin/activate` (create it with `python3.13 -m venv .venv && pip install -r requirements-dev.txt` if missing).
- Tests: `pytest` runs both `tests/` (notifier) and `tests/hof/` (this package). Test files under `tests/hof/` are named `test_hof_*.py` so their module names never collide with the notifier's tests; `tests/hof/` has no `__init__.py` on purpose, because a package named `hof` there would shadow the real `hof` package.
- Lint: `ruff check src tests scripts hof`.
- MFL calls only in the two capture tasks (5 and 11). Every other test stubs HTTP with `responses`.
- Commit after every task with the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## File structure

| Path | Responsibility |
|---|---|
| `hof/__init__.py` | package docstring |
| `hof/__main__.py` | `python -m hof fetch` (later plans add `build`, `notify`) |
| `hof/config.py` | `Config` from `data/config.toml` |
| `hof/fetch.py` | season discovery, per-season fetch into a temp dir, players chunking, `run()` |
| `hof/snapshots.py` | read `data/raw/<year>/` into a `Season` |
| `hof/model/__init__.py` | empty |
| `hof/model/players.py` | `PlayerInfo`, players export parsing |
| `hof/model/transactions.py` | typed transaction log, lock timestamps, effective week |
| `hof/model/season.py` | `Franchise`, `Lineup`, `Week`, `BracketGame`, `Standing`, `DraftPick`, `Game`, `Season`, parsers, counted games |
| `hof/stats/__init__.py` | empty |
| `hof/stats/vor.py` | `Start`, `baselines()`, `starts()` |
| `hof/requirements.txt` | runtime deps for the workflow |
| `data/config.toml` | league id, overrides, thresholds |
| `data/raw/<year>/` | snapshots (Task 11) |
| `tests/hof/conftest.py` | fixture path |
| `tests/hof/synthetic.py` | builder for small synthetic seasons |
| `tests/hof/fixtures/raw/2020/` | real 2020 responses, pruned (Task 5) |
| `tests/hof/test_hof_*.py` | tests per module |

---

### Task 1: Scaffold the `hof` package

**Files:**
- Create: `hof/__init__.py`, `hof/model/__init__.py`, `hof/stats/__init__.py`, `hof/requirements.txt`, `tests/hof/conftest.py`
- Modify: `pyproject.toml`, `requirements-dev.txt`, `.github/workflows/ci.yml`

- [ ] **Step 1: Create the package files**

`hof/__init__.py`:

```python
"""BDFL Hall of Records: fetch MFL history, compute records, build the site, post to Discord."""
```

`hof/model/__init__.py` and `hof/stats/__init__.py`: empty files.

`hof/requirements.txt` (pip resolves the nested `-r` relative to this file):

```
-r ../src/requirements.txt
jinja2>=3.1,<4
```

`tests/hof/conftest.py`:

```python
"""Shared fixtures for the hof tests."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES
```

- [ ] **Step 2: Wire the package into tooling**

`requirements-dev.txt`, add after the `-r src/requirements.txt` line:

```
-r hof/requirements.txt
```

`pyproject.toml`, change these two lines:

```toml
pythonpath = ["src", "."]
```

```toml
known-first-party = ["bdfl", "handler", "hof"]
```

`.github/workflows/ci.yml`: change `- run: ruff check src tests scripts` to `- run: ruff check src tests scripts hof`, and add `hof/requirements.txt` as a third line under `cache-dependency-path`.

- [ ] **Step 3: Install and verify nothing broke**

Run: `pip install -r requirements-dev.txt && ruff check src tests scripts hof && pytest`
Expected: install succeeds (jinja2 appears), ruff reports no issues, every existing notifier test passes.

- [ ] **Step 4: Commit**

```bash
git add hof pyproject.toml requirements-dev.txt .github/workflows/ci.yml tests/hof/conftest.py
git commit -m "chore: scaffold the hof package

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `MflClient.export()`

**Files:**
- Modify: `src/bdfl/mfl.py` (after the `players` method, about line 95)
- Test: `tests/test_mfl.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_mfl.py`:

```python
@responses.activate
def test_export_passes_params_and_returns_body():
    responses.get(
        f"{BASE_URL}/2020/export",
        json={"weeklyResults": {"week": "1"}},
        match=[
            responses.matchers.query_param_matcher(
                {"TYPE": "weeklyResults", "L": LEAGUE_ID, "JSON": "1", "W": "1"}
            )
        ],
    )
    assert make_client().export(2020, "weeklyResults", W="1") == {"weeklyResults": {"week": "1"}}


@responses.activate
def test_export_raises_on_error_body():
    responses.get(f"{BASE_URL}/2016/export", json={"error": {"$t": "Invalid league ID 65522"}})
    with pytest.raises(MflError, match="Invalid league ID"):
        make_client().export(2016, "league")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_mfl.py -k export -v`
Expected: 2 failures with `AttributeError: 'MflClient' object has no attribute 'export'`.

- [ ] **Step 3: Implement**

In `src/bdfl/mfl.py`, add after the `players` method inside the public API section:

```python
    def export(self, year: int, type_: str, **params: str) -> dict[str, Any]:
        """Fetch any export TYPE for a year and return the parsed body.

        Raises MflError on an error body; the hall of records uses this for every export
        the notifier does not need by name.
        """
        return self._require_ok(self._get(year, type_, **params), type_)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_mfl.py -v`
Expected: all pass, including the two new ones.

- [ ] **Step 5: Commit**

```bash
git add src/bdfl/mfl.py tests/test_mfl.py
git commit -m "feat(mfl): add export() for arbitrary export types

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Configuration

**Files:**
- Create: `data/config.toml`, `hof/config.py`
- Test: `tests/hof/test_hof_config.py`

- [ ] **Step 1: Write the config file**

`data/config.toml`:

```toml
# Hall of Records configuration. Read by `python -m hof`; see docs/superpowers/specs/2026-09-06-hall-of-records-design.md section 5.

[league]
id = "65522"
site_base_url = "https://btcookies.github.io/bdfl-trade-notifier/"

# Seasons that lived under a different MFL league id.
[seasons.overrides]
2016 = "79873"

[hall_of_fame]
player_min_vor = 400.0
player_min_starts = 30
franchise_min_titles = 2
watch_list_margin = 100.0

# Optional manager names, shown on franchise pages when present. Repeat the block per entry.
# [[managers]]
# franchise = "0001"
# name = "Example Name"
# from = 2016
```

- [ ] **Step 2: Write the failing tests**

`tests/hof/test_hof_config.py`:

```python
from pathlib import Path

import pytest

from hof.config import Config, ConfigError, HallRules, Manager

REPO_CONFIG = Path(__file__).resolve().parents[2] / "data" / "config.toml"


def test_loads_the_repo_config():
    config = Config.load(REPO_CONFIG)
    assert config.league_id == "65522"
    assert config.site_base_url == "https://btcookies.github.io/bdfl-trade-notifier/"
    assert config.league_id_for(2016) == "79873"
    assert config.league_id_for(2020) == "65522"
    assert config.hall == HallRules(400.0, 30, 2, 100.0)
    assert config.managers == ()


def test_from_dict_applies_defaults_and_normalizes_base_url():
    config = Config.from_dict({"league": {"id": "1", "site_base_url": "https://x.test"}})
    assert config.site_base_url == "https://x.test/"
    assert config.league_overrides == {}
    assert config.hall == HallRules()


def test_managers_are_parsed():
    config = Config.from_dict(
        {
            "league": {"id": "1", "site_base_url": "https://x.test/"},
            "managers": [{"franchise": "0001", "name": " Pat ", "from": 2016}],
        }
    )
    assert config.managers == (Manager("0001", "Pat", 2016),)


@pytest.mark.parametrize(
    "raw, message",
    [
        ({"league": {"site_base_url": "https://x.test/"}}, "league.id"),
        ({"league": {"id": "1", "site_base_url": "http://x.test/"}}, "site_base_url"),
        ({"league": {"id": "1", "site_base_url": "https://x.test/"}, "seasons": {"overrides": {"abc": "1"}}}, "overrides"),
        ({"league": {"id": "1", "site_base_url": "https://x.test/"}, "managers": [{"name": "x"}]}, "managers"),
    ],
)
def test_invalid_config_raises(raw, message):
    with pytest.raises(ConfigError, match=message):
        Config.from_dict(raw)


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError, match="missing"):
        Config.load(tmp_path / "config.toml")
```

- [ ] **Step 3: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_config.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'hof.config'`.

- [ ] **Step 4: Implement**

`hof/config.py`:

```python
"""Configuration for the hall of records, read from data/config.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """The config file is missing, malformed, or has an invalid value."""


@dataclass(frozen=True)
class HallRules:
    player_min_vor: float = 400.0
    player_min_starts: int = 30
    franchise_min_titles: int = 2
    watch_list_margin: float = 100.0


@dataclass(frozen=True)
class Manager:
    franchise: str
    name: str
    from_year: int


@dataclass(frozen=True)
class Config:
    league_id: str
    site_base_url: str
    league_overrides: dict[int, str]
    hall: HallRules
    managers: tuple[Manager, ...]

    def league_id_for(self, year: int) -> str:
        return self.league_overrides.get(year, self.league_id)

    @classmethod
    def load(cls, path: Path) -> Config:
        try:
            raw = tomllib.loads(path.read_text())
        except FileNotFoundError:
            raise ConfigError(f"missing config file {path}") from None
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Config:
        league = raw.get("league") or {}
        league_id = str(league.get("id") or "").strip()
        if not league_id.isdigit():
            raise ConfigError("league.id must be the numeric MFL league id")
        base_url = str(league.get("site_base_url") or "").strip()
        if not base_url.startswith("https://"):
            raise ConfigError("league.site_base_url must be an https URL")
        if not base_url.endswith("/"):
            base_url += "/"

        overrides: dict[int, str] = {}
        for year, league in ((raw.get("seasons") or {}).get("overrides") or {}).items():
            if not str(year).isdigit() or not str(league).isdigit():
                raise ConfigError(f"seasons.overrides: bad entry {year!r} = {league!r}")
            overrides[int(year)] = str(league)

        hall_raw = raw.get("hall_of_fame") or {}
        try:
            hall = HallRules(
                player_min_vor=float(hall_raw.get("player_min_vor", HallRules.player_min_vor)),
                player_min_starts=int(hall_raw.get("player_min_starts", HallRules.player_min_starts)),
                franchise_min_titles=int(
                    hall_raw.get("franchise_min_titles", HallRules.franchise_min_titles)
                ),
                watch_list_margin=float(
                    hall_raw.get("watch_list_margin", HallRules.watch_list_margin)
                ),
            )
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"hall_of_fame: {exc}") from exc

        managers = []
        for entry in raw.get("managers") or []:
            try:
                managers.append(
                    Manager(
                        franchise=str(entry["franchise"]),
                        name=str(entry["name"]).strip(),
                        from_year=int(entry.get("from", 0)),
                    )
                )
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                raise ConfigError(f"managers: bad entry {entry!r}") from exc

        return cls(league_id, base_url, overrides, hall, tuple(managers))
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/hof/test_hof_config.py -v`
Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add data/config.toml hof/config.py tests/hof/test_hof_config.py
git commit -m "feat(hof): config file and loader

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Fetching snapshots

**Files:**
- Create: `hof/fetch.py`
- Test: `tests/hof/test_hof_fetch.py`

- [ ] **Step 1: Write the failing tests**

`tests/hof/test_hof_fetch.py`:

```python
import json
import re
import urllib.parse
from datetime import UTC, date, datetime

import pytest
import responses

from bdfl.mfl import BASE_URL, MflClient, MflError
from hof import fetch
from hof.config import Config, HallRules

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
CONFIG = Config(
    league_id="65522",
    site_base_url="https://example.test/",
    league_overrides={2016: "79873"},
    hall=HallRules(),
    managers=(),
)


def league_body(league_id, years, end_week=2):
    return {
        "league": {
            "id": league_id,
            "name": "BDFL",
            "startWeek": "1",
            "endWeek": str(end_week),
            "history": {"league": [{"year": str(y), "url": f"https://x/{y}"} for y in years]},
            "franchises": {"franchise": [{"id": "0001", "name": "A"}, {"id": "0002", "name": "B"}]},
        }
    }


def week_body(week):
    return {
        "weeklyResults": {
            "week": str(week),
            "matchup": [
                {
                    "franchise": [
                        {
                            "id": "0001",
                            "score": "10.0",
                            "starters": "101,102,",
                            "nonstarters": "103,",
                            "player": [{"id": "101", "score": "5.0", "status": "starter"}],
                        },
                        {
                            "id": "0002",
                            "score": "8.0",
                            "starters": "104,",
                            "nonstarters": "",
                            "player": [{"id": "104", "score": "8.0", "status": "starter"}],
                        },
                    ]
                }
            ],
        }
    }


def players_body(query):
    ids = query["PLAYERS"].split(",")
    return {
        "players": {
            "player": [
                {"id": i, "name": f"Last{i}, First", "position": "RB", "team": "SF"} for i in ids
            ]
        }
    }


def season_handlers(year, league_id, years, weeks=2):
    return {
        (year, "league"): league_body(league_id, years, end_week=weeks),
        (year, "standings"): {"leagueStandings": {"franchise": []}},
        (year, "schedule"): {"schedule": {"weeklySchedule": []}},
        (year, "playoffBrackets"): {"playoffBrackets": {}},
        (year, "playoffBracket"): {"playoffBracket": {"bracket_id": "1", "playoffRound": []}},
        (year, "draftResults"): {
            "draftResults": {
                "draftUnit": {
                    "draftPick": [
                        {"round": "01", "pick": "01", "franchise": "0001", "player": "201", "timestamp": "1"}
                    ]
                }
            }
        },
        (year, "transactions"): {
            "transactions": {
                "transaction": [
                    {
                        "type": "TRADE",
                        "timestamp": "5",
                        "franchise": "0001",
                        "franchise2": "0002",
                        "franchise1_gave_up": "301,",
                        "franchise2_gave_up": "BB_5,",
                    }
                ]
            }
        },
        (year, "weeklyResults"): lambda q: week_body(int(q["W"])),
        (year, "players"): players_body,
    }


def stub_mfl(handlers):
    """Route every MFL GET to handlers[(year, TYPE)]: a body, or a callable taking the query."""

    def callback(request):
        parsed = urllib.parse.urlparse(request.url)
        query = dict(urllib.parse.parse_qsl(parsed.query))
        year = int(parsed.path.split("/")[1])
        handler = handlers.get((year, query["TYPE"]))
        if handler is None:
            body = {"error": {"$t": f"no stub for {year} {query['TYPE']}"}}
        else:
            body = handler(query) if callable(handler) else handler
        return 200, {"Content-Type": "application/json"}, json.dumps(body)

    responses.add_callback(
        responses.GET, re.compile(rf"{re.escape(BASE_URL)}/\d{{4}}/export.*"), callback=callback
    )


def requested(year=None, type_=None):
    """Query dicts of every MFL call made so far, optionally filtered."""
    out = []
    for call in responses.calls:
        parsed = urllib.parse.urlparse(call.request.url)
        query = dict(urllib.parse.parse_qsl(parsed.query))
        called_year = int(parsed.path.split("/")[1])
        if (year is None or called_year == year) and (type_ is None or query["TYPE"] == type_):
            out.append(query)
    return out


def make_factory():
    def factory(league_id):
        return MflClient(league_id=league_id, user_agent="test", sleep=lambda s: None)

    return factory


SEASON_FILES = [
    "league.json",
    "standings.json",
    "schedule.json",
    "playoffBrackets.json",
    "playoffBracket-1.json",
    "draftResults.json",
    "transactions.json",
    "players.json",
    "meta.json",
    "weeklyResults/W01.json",
    "weeklyResults/W02.json",
]


@responses.activate
def test_run_fetches_every_season_in_history_with_league_id_overrides(tmp_path):
    stub_mfl({**season_handlers(2026, "65522", [2016, 2026]), **season_handlers(2016, "79873", [2016, 2026])})

    fetched = fetch.run(tmp_path, CONFIG, NOW, make_factory())

    assert fetched == [2016, 2026]
    assert {q["L"] for q in requested(2016)} == {"79873"}
    assert {q["L"] for q in requested(2026)} == {"65522"}
    for year in (2016, 2026):
        for name in SEASON_FILES:
            assert (tmp_path / "raw" / str(year) / name).exists(), f"{year}/{name}"
    assert json.loads((tmp_path / "raw" / "2016" / "meta.json").read_text())["complete"] is True
    meta_2026 = json.loads((tmp_path / "raw" / "2026" / "meta.json").read_text())
    assert meta_2026["complete"] is False
    assert meta_2026["league_id"] == "65522"
    players = json.loads((tmp_path / "raw" / "2026" / "players.json").read_text())
    assert {p["id"] for p in players["players"]["player"]} == {"101", "102", "103", "104", "201", "301"}
    assert not list((tmp_path / "raw").glob(".*.tmp"))


@responses.activate
def test_run_skips_seasons_marked_complete(tmp_path):
    done = tmp_path / "raw" / "2016"
    done.mkdir(parents=True)
    (done / "meta.json").write_text(json.dumps({"complete": True}))
    stub_mfl(season_handlers(2026, "65522", [2016, 2026]))

    assert fetch.run(tmp_path, CONFIG, NOW, make_factory()) == [2026]
    assert requested(2016) == []


@responses.activate
def test_run_honors_an_explicit_year_list(tmp_path):
    stub_mfl(season_handlers(2020, "65522", [2020]))

    assert fetch.run(tmp_path, CONFIG, NOW, make_factory(), years=[2020]) == [2020]
    assert requested(2026) == []


@responses.activate
def test_fetch_season_replaces_nothing_when_a_request_fails(tmp_path):
    season_dir = tmp_path / "raw" / "2026"
    season_dir.mkdir(parents=True)
    (season_dir / "marker").write_text("old")
    handlers = season_handlers(2026, "65522", [2026])
    handlers[(2026, "weeklyResults")] = lambda q: (
        {"error": {"$t": "boom"}} if q["W"] == "2" else week_body(1)
    )
    stub_mfl(handlers)

    with pytest.raises(MflError, match="boom"):
        fetch.fetch_season(make_factory()("65522"), 2026, season_dir, NOW)

    assert (season_dir / "marker").read_text() == "old"
    assert not (season_dir / "league.json").exists()
    assert not list((tmp_path / "raw").glob(".*.tmp"))


@responses.activate
def test_players_are_requested_in_chunks_of_200():
    stub_mfl({(2026, "players"): players_body})
    ids = {str(i) for i in range(450)}

    body = fetch.fetch_players(make_factory()("65522"), 2026, ids)

    sizes = [len(q["PLAYERS"].split(",")) for q in requested(2026, "players")]
    assert sizes == [200, 200, 50]
    assert {p["id"] for p in body["players"]["player"]} == ids


def test_referenced_player_ids_covers_lineups_draft_and_transactions():
    weekly = [week_body(1)]
    draft = {"draftResults": {"draftUnit": {"draftPick": [{"player": "201"}]}}}
    transactions = {
        "transactions": {
            "transaction": [
                {"type": "TRADE", "franchise1_gave_up": "301,BB_5,", "franchise2_gave_up": "FP_0001_2027_1,"},
                {"type": "BBID_WAIVER", "transaction": "401,|3.00|402,"},
                {"type": "FREE_AGENT", "transaction": "|403,"},
                {"type": "IR", "activated": "404,", "deactivated": ""},
                {"type": "TAXI", "promoted": "", "demoted": "405,"},
            ]
        }
    }
    assert fetch.referenced_player_ids(weekly, draft, transactions) == {
        "101", "102", "103", "104", "201", "301", "401", "402", "403", "404", "405"
    }


def test_season_complete_on_february_first_of_the_next_year():
    assert fetch.season_complete(2025, date(2026, 1, 31)) is False
    assert fetch.season_complete(2025, date(2026, 2, 1)) is True


@responses.activate
def test_discover_seasons_falls_back_to_the_prior_year():
    responses.get(f"{BASE_URL}/2026/export", status=404)
    stub_mfl({(2025, "league"): league_body("65522", [2024, 2025])})

    assert fetch.discover_seasons(make_factory()("65522"), NOW) == [2024, 2025]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_fetch.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'hof.fetch'`.

- [ ] **Step 3: Implement**

`hof/fetch.py`:

```python
"""Fetch raw MFL exports for every season into data/raw/<year>/.

Completed seasons are fetched once and never touched again. The current season is refetched
in full on every run so stat corrections flow through. A season directory is replaced only
after every request for it succeeded.
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Callable, Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from bdfl.mfl import LeagueNotFound, MflClient
from bdfl.models import as_list, split_assets
from hof.config import Config

log = logging.getLogger(__name__)

USER_AGENT = "bdfl-hof/1.0 (+https://github.com/btcookies/bdfl-trade-notifier)"
PLAYERS_CHUNK = 200
TRANSACTIONS_DAYS = "400"

# (file name, TYPE, extra params). Weekly results and players are fetched separately.
SEASON_EXPORTS: tuple[tuple[str, str, dict[str, str]], ...] = (
    ("league.json", "league", {}),
    ("standings.json", "standings", {}),
    ("schedule.json", "schedule", {}),
    ("playoffBrackets.json", "playoffBrackets", {}),
    ("playoffBracket-1.json", "playoffBracket", {"BRACKET_ID": "1"}),
    ("draftResults.json", "draftResults", {}),
    ("transactions.json", "transactions", {"TRANS_TYPE": "*", "DAYS": TRANSACTIONS_DAYS}),
)

ClientFactory = Callable[[str], MflClient]


def season_complete(year: int, today: date) -> bool:
    """A season is frozen once February of the following year arrives."""
    return today >= date(year + 1, 2, 1)


def discover_seasons(client: MflClient, now: datetime) -> list[int]:
    """Every season year in the current league's history, oldest first."""
    for year in (now.year, now.year - 1):
        league = client.league(year)
        if league is None:
            continue
        years = {
            int(entry["year"])
            for entry in as_list((league.get("history") or {}).get("league"))
            if str(entry.get("year", "")).isdigit()
        }
        years.add(year)
        return sorted(years)
    raise LeagueNotFound(f"league {client.league_id} not found for {now.year} or {now.year - 1}")


def is_fetched_complete(season_dir: Path) -> bool:
    meta = season_dir / "meta.json"
    if not meta.exists():
        return False
    try:
        return bool(json.loads(meta.read_text()).get("complete"))
    except (ValueError, OSError):
        return False


def write_json(path: Path, body: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=1, sort_keys=True, ensure_ascii=False) + "\n")


def _lineups(weekly_body: dict[str, Any]) -> list[dict[str, Any]]:
    results = weekly_body.get("weeklyResults") or {}
    matchup_lineups = [
        franchise
        for matchup in as_list(results.get("matchup"))
        for franchise in as_list(matchup.get("franchise"))
    ]
    return matchup_lineups + as_list(results.get("franchise"))


def referenced_player_ids(
    weekly: Iterable[dict[str, Any]], draft: dict[str, Any], transactions: dict[str, Any]
) -> set[str]:
    """Every player id a season's lineups, draft, and transaction log mention."""
    ids: set[str] = set()
    for body in weekly:
        for lineup in _lineups(body):
            ids.update(split_assets(lineup.get("starters")))
            ids.update(split_assets(lineup.get("nonstarters")))
            ids.update(str(p["id"]) for p in as_list(lineup.get("player")) if "id" in p)
    for unit in as_list((draft.get("draftResults") or {}).get("draftUnit")):
        ids.update(str(p["player"]) for p in as_list(unit.get("draftPick")) if p.get("player"))
    for tx in as_list((transactions.get("transactions") or {}).get("transaction")):
        for key in ("franchise1_gave_up", "franchise2_gave_up", "activated", "deactivated", "promoted", "demoted"):
            ids.update(split_assets(tx.get(key)))
        for part in str(tx.get("transaction") or "").split("|"):
            ids.update(split_assets(part))
    return {i for i in ids if i.isdigit()}


def fetch_players(client: MflClient, year: int, ids: Iterable[str]) -> dict[str, Any]:
    """One merged players export for the ids, requested in chunks of PLAYERS_CHUNK."""
    wanted = sorted(set(ids))
    players: list[dict[str, Any]] = []
    for start in range(0, len(wanted), PLAYERS_CHUNK):
        chunk = wanted[start : start + PLAYERS_CHUNK]
        body = client.export(year, "players", PLAYERS=",".join(chunk))
        players.extend(as_list((body.get("players") or {}).get("player")))
    return {"players": {"player": players}}


def fetch_season(client: MflClient, year: int, season_dir: Path, now: datetime) -> None:
    """Fetch every export for one season, replacing season_dir only on full success."""
    tmp = season_dir.parent / f".{year}.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    try:
        bodies: dict[str, dict[str, Any]] = {}
        for name, type_, params in SEASON_EXPORTS:
            bodies[name] = client.export(year, type_, **params)
            write_json(tmp / name, bodies[name])
        league = bodies["league.json"].get("league") or {}
        start_week = int(league.get("startWeek") or 1)
        end_week = int(league.get("endWeek") or 17)
        weekly: list[dict[str, Any]] = []
        for week in range(start_week, end_week + 1):
            body = client.export(year, "weeklyResults", W=str(week))
            write_json(tmp / "weeklyResults" / f"W{week:02d}.json", body)
            weekly.append(body)
        ids = referenced_player_ids(weekly, bodies["draftResults.json"], bodies["transactions.json"])
        write_json(tmp / "players.json", fetch_players(client, year, ids))
        write_json(
            tmp / "meta.json",
            {
                "league_id": client.league_id,
                "complete": season_complete(year, now.date()),
                "fetched_at": now.isoformat(timespec="seconds"),
                "weeks": [start_week, end_week],
            },
        )
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    if season_dir.exists():
        shutil.rmtree(season_dir)
    tmp.rename(season_dir)


def run(
    data_dir: Path,
    config: Config,
    now: datetime,
    client_factory: ClientFactory,
    years: Iterable[int] | None = None,
) -> list[int]:
    """Fetch every season not already complete on disk; return the years fetched, ascending."""
    raw = data_dir / "raw"
    current = client_factory(config.league_id)
    wanted = sorted(years) if years is not None else discover_seasons(current, now)
    fetched: list[int] = []
    for year in wanted:
        season_dir = raw / str(year)
        if is_fetched_complete(season_dir):
            log.info("season %s already complete; skipping", year)
            continue
        league_id = config.league_id_for(year)
        client = current if league_id == config.league_id else client_factory(league_id)
        log.info("fetching season %s from league %s", year, league_id)
        fetch_season(client, year, season_dir, now)
        fetched.append(year)
    return fetched
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/hof/test_hof_fetch.py -v`
Expected: 8 passed.

- [ ] **Step 5: Lint and commit**

Run: `ruff check hof tests/hof`
Expected: no issues.

```bash
git add hof/fetch.py tests/hof/test_hof_fetch.py
git commit -m "feat(hof): fetch season snapshots from MFL

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Command line and the 2020 fixture capture

**Files:**
- Create: `hof/__main__.py`, `tests/hof/fixtures/raw/2020/` (captured)
- Test: `tests/hof/test_hof_cli.py`

- [ ] **Step 1: Write the failing test**

`tests/hof/test_hof_cli.py`:

```python
from pathlib import Path

import pytest

from hof import __main__ as cli
from hof.config import ConfigError

CONFIG = Path(__file__).resolve().parents[2] / "data" / "config.toml"


def test_fetch_command_calls_run_with_years(monkeypatch, tmp_path, capsys):
    seen = {}

    def fake_run(data_dir, config, now, client_factory, years=None):
        seen.update(data_dir=data_dir, league=config.league_id, years=years)
        assert client_factory("79873").league_id == "79873"
        return [2020]

    monkeypatch.setattr(cli.fetch, "run", fake_run)

    code = cli.main(["--data", str(tmp_path), "--config", str(CONFIG), "fetch", "--year", "2020"])

    assert code == 0
    assert seen == {"data_dir": tmp_path, "league": "65522", "years": [2020]}
    assert "fetched 1 season(s): [2020]" in capsys.readouterr().out


def test_missing_config_is_a_clean_error(tmp_path):
    with pytest.raises(ConfigError):
        cli.main(["--data", str(tmp_path), "fetch"])
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/hof/test_hof_cli.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'hof.__main__'`.

- [ ] **Step 3: Implement**

`hof/__main__.py`:

```python
"""Command line: python -m hof [--data DIR] [--config FILE] {fetch}."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests

from bdfl.mfl import MflClient
from hof import fetch
from hof.config import Config


def client_factory(session: requests.Session):
    """Build MFL clients that share one HTTP session; one client per league id."""

    def make(league_id: str) -> MflClient:
        return MflClient(league_id=league_id, user_agent=fetch.USER_AGENT, session=session)

    return make


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hof", description="BDFL Hall of Records")
    parser.add_argument("--data", type=Path, default=Path("data"), help="data directory (default: data)")
    parser.add_argument("--config", type=Path, help="config file (default: <data>/config.toml)")
    parser.add_argument("--log-level", default="INFO")
    commands = parser.add_subparsers(dest="command", required=True)
    fetch_parser = commands.add_parser("fetch", help="download MFL snapshots for every incomplete season")
    fetch_parser.add_argument(
        "--year", type=int, action="append", help="only this season; repeat for several"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level.upper(), format="%(levelname)s %(name)s: %(message)s")
    config = Config.load(args.config or args.data / "config.toml")

    if args.command == "fetch":
        fetched = fetch.run(
            args.data, config, datetime.now(UTC), client_factory(requests.Session()), years=args.year
        )
        print(f"fetched {len(fetched)} season(s): {fetched}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/hof/test_hof_cli.py -v`
Expected: 2 passed.

- [ ] **Step 5: Capture the 2020 season as fixtures (real network, about 30 requests)**

Run:

```bash
python -m hof --data tests/hof/fixtures --config data/config.toml fetch --year 2020
```

Expected output ends with `fetched 1 season(s): [2020]` after roughly 30 seconds. Then prune to the weeks the tests need (a regular-season week, the last regular-season week, the three bracket weeks, and the non-bracket week 17):

```bash
find tests/hof/fixtures/raw/2020/weeklyResults -name 'W*.json' ! -name 'W01.json' ! -name 'W13.json' ! -name 'W14.json' ! -name 'W15.json' ! -name 'W16.json' ! -name 'W17.json' -delete
ls tests/hof/fixtures/raw/2020 tests/hof/fixtures/raw/2020/weeklyResults
du -sh tests/hof/fixtures
```

Expected: the season directory holds the nine files plus `weeklyResults/` with exactly W01, W13, W14, W15, W16, W17; total under 400 KB. Spot-check two facts the later tests rely on:

```bash
python -c "
import json
b = json.load(open('tests/hof/fixtures/raw/2020/playoffBracket-1.json'))['playoffBracket']
print([ (r['week'], len(r['playoffGame']) if isinstance(r['playoffGame'], list) else 1) for r in b['playoffRound'] ])
w = json.load(open('tests/hof/fixtures/raw/2020/weeklyResults/W01.json'))['weeklyResults']
print(len(w['matchup']), w['matchup'][0]['franchise'][0]['id'], w['matchup'][0]['franchise'][0]['score'])
"
```

Expected: `[('14', 2), ('15', 2), ('16', 1)]` and `6 0009 104.8`. If MFL has changed the 2020 data, adjust the expected values in Tasks 7 to 9 to what this prints.

- [ ] **Step 6: Commit**

```bash
git add hof/__main__.py tests/hof/test_hof_cli.py tests/hof/fixtures
git commit -m "feat(hof): fetch command and 2020 test fixtures

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Player model

**Files:**
- Create: `hof/model/players.py`
- Test: `tests/hof/test_hof_players.py`

- [ ] **Step 1: Write the failing tests**

`tests/hof/test_hof_players.py`:

```python
import json

from hof.model.players import UNKNOWN_POSITION, PlayerInfo, parse_players


def test_parses_the_2020_players_snapshot(fixtures_dir):
    body = json.loads((fixtures_dir / "raw" / "2020" / "players.json").read_text())
    players = parse_players(body)
    assert len(players) > 300
    ryan = players["9099"]
    assert ryan == PlayerInfo(id="9099", name="Matt Ryan", position="QB", team="ATL")


def test_parse_handles_single_player_dict_and_missing_fields():
    body = {"players": {"player": {"id": " 7 ", "name": "Doe, Jane"}}}
    assert parse_players(body) == {"7": PlayerInfo("7", "Jane Doe", UNKNOWN_POSITION, "")}


def test_unknown_player_placeholder():
    unknown = PlayerInfo.unknown("42")
    assert unknown.name == "Unknown player (#42)"
    assert unknown.position == UNKNOWN_POSITION
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_players.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'hof.model.players'`.

- [ ] **Step 3: Implement**

`hof/model/players.py`:

```python
"""Player identity for one season, from that season's players snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bdfl.assets import format_player_name
from bdfl.models import as_list

UNKNOWN_POSITION = "UNK"


@dataclass(frozen=True)
class PlayerInfo:
    id: str
    name: str
    position: str
    team: str

    @classmethod
    def unknown(cls, player_id: str) -> PlayerInfo:
        return cls(id=player_id, name=f"Unknown player (#{player_id})", position=UNKNOWN_POSITION, team="")


def parse_players(body: dict[str, Any]) -> dict[str, PlayerInfo]:
    """Player id to PlayerInfo; MFL's 'Last, First' becomes 'First Last'."""
    players: dict[str, PlayerInfo] = {}
    for raw in as_list((body.get("players") or {}).get("player")):
        if "id" not in raw:
            continue
        player_id = str(raw["id"]).strip()
        name = format_player_name(str(raw.get("name") or ""))
        players[player_id] = PlayerInfo(
            id=player_id,
            name=name or f"Unknown player (#{player_id})",
            position=str(raw.get("position") or UNKNOWN_POSITION).strip(),
            team=str(raw.get("team") or "").strip(),
        )
    return players
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/hof/test_hof_players.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add hof/model/players.py tests/hof/test_hof_players.py
git commit -m "feat(hof): player model

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Transaction log model

**Files:**
- Create: `hof/model/transactions.py`
- Test: `tests/hof/test_hof_transactions.py`

- [ ] **Step 1: Write the failing tests**

`tests/hof/test_hof_transactions.py`:

```python
import json

import pytest

from hof.model.transactions import (
    FreeAgentMove,
    RosterMove,
    Trade,
    TransactionLog,
    WaiverClaim,
    parse_transactions,
)


@pytest.fixture
def log_2020(fixtures_dir) -> TransactionLog:
    body = json.loads((fixtures_dir / "raw" / "2020" / "transactions.json").read_text())
    return parse_transactions(body)


def test_counts_by_type_match_the_2020_log(log_2020):
    assert len(log_2020.trades) == 20
    assert len(log_2020.waivers) == 97
    assert len(log_2020.free_agents) == 147
    assert len(log_2020.roster_moves) == 288
    assert len(log_2020.lock_times) == 17


def test_entries_are_sorted_by_timestamp(log_2020):
    for group in (log_2020.trades, log_2020.waivers, log_2020.free_agents, log_2020.roster_moves):
        stamps = [entry.timestamp for entry in group]
        assert stamps == sorted(stamps)
    assert list(log_2020.lock_times) == sorted(log_2020.lock_times)


def test_first_2020_trade(log_2020):
    first = log_2020.trades[0]
    assert first == Trade(
        timestamp=1594133412,
        franchise1="0001",
        franchise2="0008",
        gave_up1=("DP_0_10", "DP_1_11", "FP_0001_2021_2"),
        gave_up2=("DP_0_4",),
        comments="",
    )


def test_effective_week_uses_lock_timestamps(log_2020):
    first_lock, second_lock = log_2020.lock_times[0], log_2020.lock_times[1]
    assert log_2020.effective_week(first_lock - 1, start_week=1) == 1
    assert log_2020.effective_week(first_lock, start_week=1) == 2
    assert log_2020.effective_week(second_lock - 1, start_week=1) == 2
    assert log_2020.effective_week(log_2020.lock_times[-1], start_week=1) is None
    assert log_2020.week_locked_at(1, start_week=1) == first_lock
    assert log_2020.week_locked_at(99, start_week=1) is None


def test_parses_each_transaction_shape():
    body = {
        "transactions": {
            "transaction": [
                {"type": "BBID_WAIVER", "timestamp": "10", "franchise": "0003", "transaction": "14209,|1.00|"},
                {"type": "BBID_WAIVER", "timestamp": "11", "franchise": "0003", "transaction": "1,|2.50|2,"},
                {"type": "FREE_AGENT", "timestamp": "12", "franchise": "0003", "transaction": "|13133,"},
                {"type": "FREE_AGENT", "timestamp": "13", "franchise": "0004", "transaction": "5,6,|7,"},
                {"type": "IR", "timestamp": "14", "franchise": "0008", "activated": "11783,", "deactivated": "11182,"},
                {"type": "TAXI", "timestamp": "15", "franchise": "0006", "promoted": "", "demoted": "14087,"},
                {"type": "LOCK_ALL_PLAYERS", "timestamp": "20", "franchise": ""},
                {"type": "UNLOCK_ALL_PLAYERS", "timestamp": "30", "franchise": ""},
                {"type": "BBID_AUTO_PROCESS_WAIVERS", "timestamp": "31", "franchise": ""},
                {"type": "TRADE", "timestamp": "not a number", "franchise": "0001", "franchise2": "0002"},
            ]
        }
    }
    log = parse_transactions(body)
    assert log.waivers == (
        WaiverClaim(10, "0003", "14209", "1.00", None),
        WaiverClaim(11, "0003", "1", "2.50", "2"),
    )
    assert log.free_agents == (
        FreeAgentMove(12, "0003", (), ("13133",)),
        FreeAgentMove(13, "0004", ("5", "6"), ("7",)),
    )
    assert log.roster_moves == (
        RosterMove(14, "0008", "IR", ("11182",), ("11783",)),
        RosterMove(15, "0006", "TAXI", ("14087",), ()),
    )
    assert log.lock_times == (20,)
    assert log.trades == ()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_transactions.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'hof.model.transactions'`.

- [ ] **Step 3: Implement**

`hof/model/transactions.py`:

```python
"""Typed view of one season's MFL transaction log."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from bdfl.models import WAIVER_RE, as_list, split_assets

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Trade:
    timestamp: int
    franchise1: str
    franchise2: str
    gave_up1: tuple[str, ...]  # asset codes franchise1 sent to franchise2
    gave_up2: tuple[str, ...]
    comments: str


@dataclass(frozen=True)
class WaiverClaim:
    timestamp: int
    franchise: str
    added: str
    bid: str
    dropped: str | None


@dataclass(frozen=True)
class FreeAgentMove:
    timestamp: int
    franchise: str
    added: tuple[str, ...]
    dropped: tuple[str, ...]


@dataclass(frozen=True)
class RosterMove:
    """An IR or taxi-squad move: `on` went onto the squad, `off` came off it."""

    timestamp: int
    franchise: str
    kind: str  # "IR" or "TAXI"
    on: tuple[str, ...]
    off: tuple[str, ...]


@dataclass(frozen=True)
class TransactionLog:
    trades: tuple[Trade, ...]
    waivers: tuple[WaiverClaim, ...]
    free_agents: tuple[FreeAgentMove, ...]
    roster_moves: tuple[RosterMove, ...]
    lock_times: tuple[int, ...]  # LOCK_ALL_PLAYERS timestamps ascending; the k-th is week start_week + k - 1

    def week_locked_at(self, week: int, start_week: int) -> int | None:
        index = week - start_week
        if 0 <= index < len(self.lock_times):
            return self.lock_times[index]
        return None

    def effective_week(self, timestamp: int, start_week: int) -> int | None:
        """First week whose lock is after the timestamp; None once the season's last lock has passed."""
        for index, lock in enumerate(self.lock_times):
            if lock > timestamp:
                return start_week + index
        return None


def parse_transactions(body: dict[str, Any]) -> TransactionLog:
    trades: list[Trade] = []
    waivers: list[WaiverClaim] = []
    free_agents: list[FreeAgentMove] = []
    moves: list[RosterMove] = []
    locks: list[int] = []
    for raw in as_list((body.get("transactions") or {}).get("transaction")):
        kind = raw.get("type")
        try:
            timestamp = int(raw["timestamp"])
            if kind == "TRADE":
                trades.append(
                    Trade(
                        timestamp=timestamp,
                        franchise1=raw["franchise"],
                        franchise2=raw["franchise2"],
                        gave_up1=split_assets(raw.get("franchise1_gave_up")),
                        gave_up2=split_assets(raw.get("franchise2_gave_up")),
                        comments=(raw.get("comments") or "").strip(),
                    )
                )
            elif kind == "BBID_WAIVER":
                match = WAIVER_RE.fullmatch(str(raw.get("transaction") or ""))
                if match is None:
                    log.warning("unparsable waiver %r", raw.get("transaction"))
                    continue
                waivers.append(
                    WaiverClaim(timestamp, raw["franchise"], match.group(1), match.group(2), match.group(3) or None)
                )
            elif kind == "FREE_AGENT":
                added, _, dropped = str(raw.get("transaction") or "").partition("|")
                free_agents.append(
                    FreeAgentMove(timestamp, raw["franchise"], split_assets(added), split_assets(dropped))
                )
            elif kind == "IR":
                moves.append(
                    RosterMove(timestamp, raw["franchise"], "IR", split_assets(raw.get("deactivated")), split_assets(raw.get("activated")))
                )
            elif kind == "TAXI":
                moves.append(
                    RosterMove(timestamp, raw["franchise"], "TAXI", split_assets(raw.get("demoted")), split_assets(raw.get("promoted")))
                )
            elif kind == "LOCK_ALL_PLAYERS":
                locks.append(timestamp)
        except (KeyError, ValueError, TypeError) as exc:
            log.warning("skipping unparsable %s transaction %r", kind, raw, exc_info=exc)

    def by_time(entry):
        return entry.timestamp

    return TransactionLog(
        trades=tuple(sorted(trades, key=by_time)),
        waivers=tuple(sorted(waivers, key=by_time)),
        free_agents=tuple(sorted(free_agents, key=by_time)),
        roster_moves=tuple(sorted(moves, key=by_time)),
        lock_times=tuple(sorted(locks)),
    )
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/hof/test_hof_transactions.py -v`
Expected: 5 passed. If the 2020 counts differ from the captured fixture, print them with `python -c "..."` against the fixture and correct the test to the real values; the 20 trades and 17 locks are the ones later plans depend on.

- [ ] **Step 5: Lint and commit**

Run: `ruff check hof tests/hof`
Expected: no issues.

```bash
git add hof/model/transactions.py tests/hof/test_hof_transactions.py
git commit -m "feat(hof): transaction log model with lock-based weeks

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Season model and counted games

**Files:**
- Create: `hof/model/season.py`
- Test: `tests/hof/test_hof_season.py`

- [ ] **Step 1: Write the failing tests**

`tests/hof/test_hof_season.py`:

```python
import json

import pytest

from hof.model.players import PlayerInfo
from hof.model.season import (
    BracketGame,
    Franchise,
    Game,
    Lineup,
    Season,
    Standing,
    Week,
    normalize_name,
    parse_bracket,
    parse_draft,
    parse_league,
    parse_standings,
    parse_week,
)
from hof.model.transactions import TransactionLog


def load(fixtures_dir, name):
    return json.loads((fixtures_dir / "raw" / "2020" / name).read_text())


def test_parse_league(fixtures_dir):
    settings = parse_league(load(fixtures_dir, "league.json"))
    assert settings.name == "Barbara Dodson's Fantasy League"
    assert len(settings.franchises) == 12
    assert settings.franchises["0001"] == Franchise("0001", "The Youth Academy", "02")
    assert settings.starter_minimums == {"QB": 1, "RB": 2, "WR": 2, "TE": 1}
    assert (settings.start_week, settings.end_week, settings.last_regular_season_week) == (1, 17, 13)


def test_parse_regular_season_week(fixtures_dir):
    week = parse_week(load(fixtures_dir, "weeklyResults/W01.json"), number=1)
    assert week.number == 1
    assert len(week.matchups) == 6
    assert len(week.lineups) == 12
    assert week.matchups[0] == ("0012", "0009")  # isHome=1 is listed second in the raw body
    lineup = week.lineups["0009"]
    assert lineup.score == 104.8
    assert lineup.result == "W"
    assert lineup.opt_pts == 117.7
    assert len(lineup.starters) == 8
    assert lineup.starters[0] == "9099"
    assert lineup.points("9099") == 24.9
    assert lineup.points("no-such-player") == 0.0
    assert lineup.played


def test_parse_playoff_week_keeps_every_lineup(fixtures_dir):
    week = parse_week(load(fixtures_dir, "weeklyResults/W15.json"), number=15)
    assert len(week.matchups) == 2
    assert len(week.lineups) == 12
    assert all(lineup.played for lineup in week.lineups.values())


def test_parse_unplayed_week():
    body = {
        "weeklyResults": {
            "week": "5",
            "matchup": [
                {"franchise": [{"id": "0012", "result": "T", "isHome": "0"}, {"id": "0005", "result": "T", "isHome": "1"}]}
            ],
        }
    }
    week = parse_week(body, number=5)
    assert week.matchups == (("0005", "0012"),)
    assert not week.lineups["0012"].played
    assert week.lineups["0012"].score is None


def test_parse_bracket(fixtures_dir):
    games = parse_bracket(load(fixtures_dir, "playoffBracket-1.json"))
    assert len(games) == 5
    assert games[0] == BracketGame(week=14, game_id="1", round_index=0, home_id="0001", away_id="0003", home_seed=3, away_seed=6)
    assert games[-1].week == 16
    assert games[-1].round_index == 2
    assert (games[-1].home_id, games[-1].away_id) == ("0010", "0002")


def test_parse_bracket_before_it_is_set():
    body = {"playoffBracket": {"playoffRound": [{"week": "15", "playoffGame": [{"game_id": "1", "home": {"seed": "3"}, "away": {"seed": "6"}}]}]}}
    games = parse_bracket(body)
    assert games == (BracketGame(15, "1", 0, None, None, 3, 6),)


def test_parse_standings(fixtures_dir):
    standings = parse_standings(load(fixtures_dir, "standings.json"))
    assert len(standings) == 12
    assert standings[0] == Standing("0002", 10, 3, 0, 1896.6, 1157.4, "3-1-0", "W3")
    assert standings[-1].franchise_id == "0004"


def test_parse_draft(fixtures_dir):
    picks, order = parse_draft(load(fixtures_dir, "draftResults.json"))
    assert len(picks) == 48
    assert (picks[0].round, picks[0].pick, picks[0].franchise_id, picks[0].player_id) == (1, 1, "0006", "14803")
    assert order[:3] == ("0006", "0012", "0004")


def test_normalize_name():
    assert normalize_name("  Free   Hernandez ") == "free hernandez"


# --- Season behaviour on a small synthetic season ------------------------------------------


def lineup(franchise_id, starters, result=None):
    scores = dict(starters)
    return Lineup(
        franchise_id=franchise_id,
        starters=tuple(starters),
        nonstarters=(),
        scores=scores,
        score=round(sum(scores.values()), 1),
        opt_pts=round(sum(scores.values()), 1),
        result=result,
    )


def synthetic_season():
    week1 = Week(
        number=1,
        lineups={
            "0001": lineup("0001", {"q1": 20.0}, "W"),
            "0002": lineup("0002", {"q2": 10.0}, "L"),
            "0003": lineup("0003", {"q3": 15.0}, "W"),
            "0004": lineup("0004", {"q4": 5.0}, "L"),
        },
        matchups=(("0001", "0002"), ("0003", "0004")),
    )
    week2 = Week(  # playoff week: one bracket game, one consolation matchup
        number=2,
        lineups={
            "0001": lineup("0001", {"q1": 12.0}, "L"),
            "0003": lineup("0003", {"q3": 12.5}, "W"),
            "0002": lineup("0002", {"q2": 30.0}, "W"),
            "0004": lineup("0004", {"q4": 1.0}, "L"),
        },
        matchups=(("0001", "0003"), ("0002", "0004")),
    )
    week3 = Week(number=3, lineups={}, matchups=(("0001", "0003"),))  # unplayed
    return Season(
        year=2030,
        league_id="1",
        name="Test",
        complete=False,
        franchises={f: Franchise(f, f"Team {f}") for f in ("0001", "0002", "0003", "0004")},
        starter_minimums={"QB": 1},
        start_week=1,
        end_week=3,
        last_regular_season_week=1,
        weeks={1: week1, 2: week2, 3: week3},
        bracket=(BracketGame(2, "1", 0, "0003", "0001", 1, 2),),
        standings=(),
        draft=(),
        round1_order=(),
        transactions=TransactionLog((), (), (), (), ()),
        players={p: PlayerInfo(p, p.upper(), "QB", "") for p in ("q1", "q2", "q3", "q4")},
    )


def test_games_counts_regular_matchups_and_bracket_games_only():
    season = synthetic_season()
    games = season.games()
    assert [(g.week, g.playoff, g.round_name) for g in games] == [
        (1, False, None),
        (1, False, None),
        (2, True, "Final"),
    ]
    final = games[-1]
    assert final.winner.franchise_id == "0003"
    assert final.loser.franchise_id == "0001"
    assert final.margin == 0.5
    assert final.opponent_of("0001").franchise_id == "0003"
    assert final.lineup_of("0003").score == 12.5
    assert season.champion_id == "0003"
    assert season.final == final


def test_ties_have_no_winner():
    game = Game(2030, 1, lineup("0001", {"a": 1.0}), lineup("0002", {"b": 1.0}), playoff=False)
    assert game.winner is None and game.loser is None and game.tie


def test_round_names_count_back_from_the_final():
    season = synthetic_season()
    three = Season(**{**season.__dict__, "bracket": (BracketGame(2, "1", 0, None, None, 3, 6), BracketGame(3, "2", 1, None, None, 1, None), BracketGame(4, "3", 2, None, None, None, None))})
    assert [three.round_name(i) for i in range(3)] == ["Quarterfinal", "Semifinal", "Final"]
    assert three.playoff_weeks() == {2, 3, 4}


def test_franchise_name_and_player_fallbacks():
    season = synthetic_season()
    assert season.franchise_name("0001") == "Team 0001"
    assert season.franchise_name("0099") == "Franchise 0099"
    assert season.player("zzz").name == "Unknown player (#zzz)"


@pytest.mark.parametrize("value, expected", [("104.8", 104.8), ("", None), (None, None), ("x", None)])
def test_float_or_none(value, expected):
    from hof.model.season import float_or_none

    assert float_or_none(value) == expected
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_season.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'hof.model.season'`.

- [ ] **Step 3: Implement**

`hof/model/season.py`:

```python
"""One season: franchises, weeks of lineups, counted games, bracket, standings, draft."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from bdfl.models import as_list, split_assets
from hof.model.players import PlayerInfo
from hof.model.transactions import TransactionLog

log = logging.getLogger(__name__)

ROUND_NAMES = ("Final", "Semifinal", "Quarterfinal", "Round of 16")
RESULTS = {"W", "L", "T"}


def normalize_name(name: str) -> str:
    """Casefold and collapse whitespace so era boundaries ignore cosmetic renames."""
    return re.sub(r"\s+", " ", name).strip().casefold()


def float_or_none(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def int_or_none(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class Franchise:
    id: str
    name: str
    division: str = ""


@dataclass(frozen=True)
class Lineup:
    franchise_id: str
    starters: tuple[str, ...]
    nonstarters: tuple[str, ...]
    scores: dict[str, float] = field(compare=False)  # only players MFL scored
    score: float | None = None  # franchise total; None until played
    opt_pts: float | None = None
    result: str | None = None  # W, L, T, or None

    @property
    def played(self) -> bool:
        return self.score is not None and bool(self.starters)

    def points(self, player_id: str) -> float:
        return self.scores.get(player_id, 0.0)


@dataclass(frozen=True)
class Week:
    number: int
    lineups: dict[str, Lineup]  # every lineup MFL listed, by franchise id
    matchups: tuple[tuple[str, str], ...]  # (home id, away id)


@dataclass(frozen=True)
class BracketGame:
    week: int
    game_id: str
    round_index: int  # 0 = first round
    home_id: str | None
    away_id: str | None
    home_seed: int | None
    away_seed: int | None


@dataclass(frozen=True)
class Standing:
    franchise_id: str
    wins: int
    losses: int
    ties: int
    points_for: float
    points_against: float
    division_record: str
    streak: str


@dataclass(frozen=True)
class DraftPick:
    round: int
    pick: int
    franchise_id: str
    player_id: str
    timestamp: int
    comments: str = ""


@dataclass(frozen=True)
class Game:
    year: int
    week: int
    home: Lineup
    away: Lineup
    playoff: bool
    round_name: str | None = None

    @property
    def winner(self) -> Lineup | None:
        home, away = self.home.score or 0.0, self.away.score or 0.0
        if home == away:
            return None
        return self.home if home > away else self.away

    @property
    def loser(self) -> Lineup | None:
        winner = self.winner
        if winner is None:
            return None
        return self.away if winner is self.home else self.home

    @property
    def tie(self) -> bool:
        return self.winner is None

    @property
    def margin(self) -> float:
        return round(abs((self.home.score or 0.0) - (self.away.score or 0.0)), 1)

    def lineup_of(self, franchise_id: str) -> Lineup | None:
        if self.home.franchise_id == franchise_id:
            return self.home
        if self.away.franchise_id == franchise_id:
            return self.away
        return None

    def opponent_of(self, franchise_id: str) -> Lineup | None:
        if self.home.franchise_id == franchise_id:
            return self.away
        if self.away.franchise_id == franchise_id:
            return self.home
        return None


@dataclass(frozen=True)
class Season:
    year: int
    league_id: str
    name: str
    complete: bool
    franchises: dict[str, Franchise]
    starter_minimums: dict[str, int]
    start_week: int
    end_week: int
    last_regular_season_week: int
    weeks: dict[int, Week]
    bracket: tuple[BracketGame, ...]
    standings: tuple[Standing, ...]  # in MFL's standings order
    draft: tuple[DraftPick, ...]
    round1_order: tuple[str, ...]
    transactions: TransactionLog
    players: dict[str, PlayerInfo]

    def player(self, player_id: str) -> PlayerInfo:
        return self.players.get(player_id) or PlayerInfo.unknown(player_id)

    def franchise_name(self, franchise_id: str) -> str:
        franchise = self.franchises.get(franchise_id)
        return franchise.name if franchise else f"Franchise {franchise_id}"

    @property
    def bracket_rounds(self) -> int:
        return max((g.round_index for g in self.bracket), default=-1) + 1

    def round_name(self, round_index: int) -> str:
        from_end = self.bracket_rounds - 1 - round_index
        if 0 <= from_end < len(ROUND_NAMES):
            return ROUND_NAMES[from_end]
        return f"Round {round_index + 1}"

    def playoff_weeks(self) -> set[int]:
        return {g.week for g in self.bracket}

    def games(self) -> list[Game]:
        """Counted games in week order: every regular-season matchup, then bracket games only."""
        games: list[Game] = []
        for number in sorted(self.weeks):
            week = self.weeks[number]
            if number <= self.last_regular_season_week:
                for home_id, away_id in week.matchups:
                    game = self._game(week, home_id, away_id, playoff=False)
                    if game is not None:
                        games.append(game)
                continue
            for bracket_game in self.bracket:
                if bracket_game.week != number or not bracket_game.home_id or not bracket_game.away_id:
                    continue
                pair = {bracket_game.home_id, bracket_game.away_id}
                matchup = next((m for m in week.matchups if set(m) == pair), None)
                if matchup is None:
                    log.warning("%s week %s: bracket game %s has no matchup", self.year, number, bracket_game.game_id)
                    continue
                game = self._game(week, matchup[0], matchup[1], playoff=True, round_name=self.round_name(bracket_game.round_index))
                if game is not None:
                    games.append(game)
        return games

    def _game(self, week: Week, home_id: str, away_id: str, playoff: bool, round_name: str | None = None) -> Game | None:
        home, away = week.lineups.get(home_id), week.lineups.get(away_id)
        if home is None or away is None or not home.played or not away.played:
            return None
        return Game(self.year, week.number, home, away, playoff, round_name)

    @property
    def final(self) -> Game | None:
        finals = [g for g in self.games() if g.playoff and g.round_name == "Final"]
        return finals[-1] if finals else None

    @property
    def champion_id(self) -> str | None:
        final = self.final
        if final is None or final.winner is None:
            return None
        return final.winner.franchise_id


@dataclass(frozen=True)
class LeagueSettings:
    name: str
    franchises: dict[str, Franchise]
    starter_minimums: dict[str, int]
    start_week: int
    end_week: int
    last_regular_season_week: int


def parse_league(body: dict[str, Any]) -> LeagueSettings:
    league = body.get("league") or {}
    franchises = {
        str(f["id"]): Franchise(str(f["id"]), str(f.get("name") or "").strip() or f"Franchise {f['id']}", str(f.get("division") or ""))
        for f in as_list((league.get("franchises") or {}).get("franchise"))
        if "id" in f
    }
    minimums: dict[str, int] = {}
    for position in as_list((league.get("starters") or {}).get("position")):
        name = str(position.get("name") or "").strip()
        limit = str(position.get("limit") or "1").split("-")[0]
        if name and limit.isdigit():
            minimums[name] = int(limit)
    return LeagueSettings(
        name=str(league.get("name") or "").strip(),
        franchises=franchises,
        starter_minimums=minimums,
        start_week=int_or_none(league.get("startWeek")) or 1,
        end_week=int_or_none(league.get("endWeek")) or 17,
        last_regular_season_week=int_or_none(league.get("lastRegularSeasonWeek")) or 13,
    )


def _lineup(raw: dict[str, Any]) -> Lineup:
    scores: dict[str, float] = {}
    for player in as_list(raw.get("player")):
        score = float_or_none(player.get("score"))
        if "id" in player and score is not None:
            scores[str(player["id"])] = score
    result = str(raw.get("result") or "").strip().upper()
    return Lineup(
        franchise_id=str(raw["id"]),
        starters=split_assets(raw.get("starters")),
        nonstarters=split_assets(raw.get("nonstarters")),
        scores=scores,
        score=float_or_none(raw.get("score")),
        opt_pts=float_or_none(raw.get("opt_pts")),
        result=result if result in RESULTS else None,
    )


def parse_week(body: dict[str, Any], number: int) -> Week:
    results = body.get("weeklyResults") or {}
    lineups: dict[str, Lineup] = {}
    matchups: list[tuple[str, str]] = []
    for matchup in as_list(results.get("matchup")):
        sides = [f for f in as_list(matchup.get("franchise")) if "id" in f]
        if len(sides) != 2:
            continue
        home, away = (sides[1], sides[0]) if str(sides[1].get("isHome")) == "1" else (sides[0], sides[1])
        for side in (home, away):
            lineups[str(side["id"])] = _lineup(side)
        matchups.append((str(home["id"]), str(away["id"])))
    for raw in as_list(results.get("franchise")):
        if "id" in raw and str(raw["id"]) not in lineups:
            lineups[str(raw["id"])] = _lineup(raw)
    return Week(number=number, lineups=lineups, matchups=tuple(matchups))


def parse_bracket(body: dict[str, Any]) -> tuple[BracketGame, ...]:
    games: list[BracketGame] = []
    rounds = as_list((body.get("playoffBracket") or {}).get("playoffRound"))
    for round_index, round_ in enumerate(rounds):
        week = int_or_none(round_.get("week"))
        if week is None:
            continue
        for game in as_list(round_.get("playoffGame")):
            home, away = game.get("home") or {}, game.get("away") or {}
            games.append(
                BracketGame(
                    week=week,
                    game_id=str(game.get("game_id") or len(games) + 1),
                    round_index=round_index,
                    home_id=str(home["franchise_id"]) if home.get("franchise_id") else None,
                    away_id=str(away["franchise_id"]) if away.get("franchise_id") else None,
                    home_seed=int_or_none(home.get("seed")),
                    away_seed=int_or_none(away.get("seed")),
                )
            )
    return tuple(games)


def parse_standings(body: dict[str, Any]) -> tuple[Standing, ...]:
    standings: list[Standing] = []
    for raw in as_list((body.get("leagueStandings") or {}).get("franchise")):
        if "id" not in raw:
            continue
        record = str(raw.get("h2hwlt") or "0-0-0").split("-")
        wins = int_or_none(raw.get("h2hw"))
        losses = int_or_none(raw.get("h2hl"))
        ties = int_or_none(raw.get("h2ht"))
        standings.append(
            Standing(
                franchise_id=str(raw["id"]),
                wins=wins if wins is not None else int_or_none(record[0]) or 0,
                losses=losses if losses is not None else (int_or_none(record[1]) if len(record) > 1 else 0) or 0,
                ties=ties if ties is not None else (int_or_none(record[2]) if len(record) > 2 else 0) or 0,
                points_for=float_or_none(raw.get("pf")) or 0.0,
                points_against=float_or_none(raw.get("pa")) or 0.0,
                division_record=str(raw.get("divwlt") or ""),
                streak=str(raw.get("strk") or ""),
            )
        )
    return tuple(standings)


def parse_draft(body: dict[str, Any]) -> tuple[tuple[DraftPick, ...], tuple[str, ...]]:
    picks: list[DraftPick] = []
    order: tuple[str, ...] = ()
    for unit in as_list((body.get("draftResults") or {}).get("draftUnit")):
        if not order:
            order = split_assets(unit.get("round1DraftOrder"))
        for raw in as_list(unit.get("draftPick")):
            round_, pick = int_or_none(raw.get("round")), int_or_none(raw.get("pick"))
            if round_ is None or pick is None or not raw.get("player") or not raw.get("franchise"):
                continue
            picks.append(
                DraftPick(
                    round=round_,
                    pick=pick,
                    franchise_id=str(raw["franchise"]),
                    player_id=str(raw["player"]),
                    timestamp=int_or_none(raw.get("timestamp")) or 0,
                    comments=str(raw.get("comments") or "").strip(),
                )
            )
    picks.sort(key=lambda p: (p.round, p.pick))
    return tuple(picks), order
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/hof/test_hof_season.py -v`
Expected: 16 passed. The `test_parse_regular_season_week` matchup assertion depends on which side MFL flagged `isHome`; if it fails, check the raw `isHome` values in `W01.json` and fix the expected tuple, keeping home first.

- [ ] **Step 5: Lint and commit**

Run: `ruff check hof tests/hof`
Expected: no issues.

```bash
git add hof/model/season.py tests/hof/test_hof_season.py
git commit -m "feat(hof): season model with counted games and bracket rounds

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Snapshot loader

**Files:**
- Create: `hof/snapshots.py`
- Test: `tests/hof/test_hof_snapshots.py`

- [ ] **Step 1: Write the failing tests**

`tests/hof/test_hof_snapshots.py`:

```python
import json

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


def test_counted_games_in_the_2020_fixture(fixtures_dir):
    season = load_season(fixtures_dir / "raw" / "2020")
    by_week = {}
    for game in season.games():
        by_week.setdefault(game.week, []).append(game)
    assert {week: len(games) for week, games in by_week.items()} == {1: 6, 13: 6, 14: 2, 15: 2, 16: 1}
    assert all(not g.playoff for g in by_week[1] + by_week[13])
    assert [g.round_name for g in by_week[14]] == ["Quarterfinal", "Quarterfinal"]
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_snapshots.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'hof.snapshots'`.

- [ ] **Step 3: Implement**

`hof/snapshots.py`:

```python
"""Load raw season snapshots from data/raw/<year>/ into Season objects."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from hof.model.players import parse_players
from hof.model.season import Season, parse_bracket, parse_draft, parse_league, parse_standings, parse_week
from hof.model.transactions import parse_transactions

log = logging.getLogger(__name__)

WEEK_FILE = re.compile(r"^W(\d{2})\.json$")


def read_json(path: Path) -> dict[str, Any]:
    """The parsed file, or an empty dict with a warning when it is missing or unreadable."""
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        log.warning("missing snapshot %s", path)
        return {}
    except ValueError as exc:
        log.warning("unreadable snapshot %s: %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def load_season(season_dir: Path) -> Season:
    year = int(season_dir.name)
    meta = read_json(season_dir / "meta.json")
    settings = parse_league(read_json(season_dir / "league.json"))
    weeks = {}
    for path in sorted((season_dir / "weeklyResults").glob("W*.json")):
        match = WEEK_FILE.match(path.name)
        if match is None:
            continue
        week = parse_week(read_json(path), number=int(match.group(1)))
        weeks[week.number] = week
    draft, round1_order = parse_draft(read_json(season_dir / "draftResults.json"))
    return Season(
        year=year,
        league_id=str(meta.get("league_id") or ""),
        name=settings.name,
        complete=bool(meta.get("complete")),
        franchises=settings.franchises,
        starter_minimums=settings.starter_minimums,
        start_week=settings.start_week,
        end_week=settings.end_week,
        last_regular_season_week=settings.last_regular_season_week,
        weeks=weeks,
        bracket=parse_bracket(read_json(season_dir / "playoffBracket-1.json")),
        standings=parse_standings(read_json(season_dir / "standings.json")),
        draft=draft,
        round1_order=round1_order,
        transactions=parse_transactions(read_json(season_dir / "transactions.json")),
        players=parse_players(read_json(season_dir / "players.json")),
    )


def load_all(data_dir: Path) -> list[Season]:
    """Every season under data_dir/raw, oldest first."""
    raw = data_dir / "raw"
    if not raw.exists():
        return []
    season_dirs = sorted(p for p in raw.iterdir() if p.is_dir() and p.name.isdigit())
    return [load_season(p) for p in season_dirs]
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/hof/test_hof_snapshots.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add hof/snapshots.py tests/hof/test_hof_snapshots.py
git commit -m "feat(hof): load season snapshots

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Value over replacement

**Files:**
- Create: `hof/stats/vor.py`
- Create: `tests/hof/synthetic.py`
- Test: `tests/hof/test_hof_vor.py`

- [ ] **Step 1: Create the synthetic season builder `tests/hof/synthetic.py`**

Test modules import it as `from synthetic import build_season, lineup`. That works because `tests/hof/` has no `__init__.py`, so pytest puts the directory itself on `sys.path` when it collects a test file there.

```python
"""Builders for small synthetic seasons used by the stats tests."""

from __future__ import annotations

from dataclasses import replace

from hof.model.players import PlayerInfo
from hof.model.season import BracketGame, Franchise, Lineup, Season, Week
from hof.model.transactions import TransactionLog


def lineup(
    franchise_id: str,
    starters: dict[str, float | None],
    bench: dict[str, float | None] | None = None,
    opt_pts: float | None = None,
) -> Lineup:
    """A played lineup. A None score means MFL listed the player without a score."""
    bench = bench or {}
    scores = {pid: s for pid, s in {**starters, **bench}.items() if s is not None}
    total = round(sum(starters.get(pid) or 0.0 for pid in starters), 1)
    return Lineup(
        franchise_id=franchise_id,
        starters=tuple(starters),
        nonstarters=tuple(bench),
        scores=scores,
        score=total,
        opt_pts=total if opt_pts is None else opt_pts,
        result=None,
    )


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
) -> Season:
    """weeks maps week number to (home, away) lineup pairs; results are filled from scores.

    players maps id to (name, position). names overrides franchise display names.
    """
    week_objects: dict[int, Week] = {}
    for number, games in weeks.items():
        lineups: dict[str, Lineup] = {}
        matchups: list[tuple[str, str]] = []
        for home, away in games:
            home_score, away_score = home.score or 0.0, away.score or 0.0
            if home_score == away_score:
                home_result = away_result = "T"
            else:
                home_result, away_result = ("W", "L") if home_score > away_score else ("L", "W")
            lineups[home.franchise_id] = replace(home, result=home_result)
            lineups[away.franchise_id] = replace(away, result=away_result)
            matchups.append((home.franchise_id, away.franchise_id))
        week_objects[number] = Week(number=number, lineups=lineups, matchups=tuple(matchups))
    names = names or {}
    return Season(
        year=year,
        league_id="1",
        name="Test League",
        complete=complete,
        franchises={f: Franchise(f, names.get(f, f"Team {f}")) for f in franchises},
        starter_minimums=starter_minimums or {"QB": 1, "RB": 2, "WR": 2, "TE": 1},
        start_week=min(weeks) if weeks else 1,
        end_week=max(weeks) if weeks else 1,
        last_regular_season_week=last_regular_season_week,
        weeks=week_objects,
        bracket=bracket,
        standings=(),
        draft=(),
        round1_order=(),
        transactions=transactions or TransactionLog((), (), (), (), ()),
        players={pid: PlayerInfo(pid, name, position, "") for pid, (name, position) in players.items()},
    )
```

- [ ] **Step 2: Write the failing tests**

`tests/hof/test_hof_vor.py`:

```python
from synthetic import build_season, lineup

from hof.model.season import BracketGame
from hof.stats.vor import Start, baselines, starts

PLAYERS = {
    "q1": ("QB One", "QB"),
    "q2": ("QB Two", "QB"),
    "q3": ("QB Three", "QB"),
    "q4": ("QB Four", "QB"),
    "r1": ("RB One", "RB"),
    "r2": ("RB Two", "RB"),
    "r3": ("RB Three", "RB"),
    "r4": ("RB Four", "RB"),
    "x1": ("Mystery Man", "UNK"),
}


def week_one():
    return [
        (lineup("0001", {"q1": 30.0, "r1": 12.0}), lineup("0002", {"q2": 20.0, "r2": 9.0})),
        (lineup("0003", {"q3": 10.0, "r3": 6.0}), lineup("0004", {"q4": 5.0, "r4": 3.0})),
    ]


def test_baseline_is_the_nth_best_starter_or_the_lowest_when_short():
    season = build_season(2030, PLAYERS, {1: week_one()}, last_regular_season_week=1)
    base = baselines(season)
    # Four franchises with one required QB: the 4th-best QB (5.0) is replacement level.
    assert base[(1, "QB")] == 5.0
    # Two required RBs would want the 8th-best, but only four started: the lowest (3.0) is used.
    assert base[(1, "RB")] == 3.0


def test_start_values_subtract_the_baseline():
    season = build_season(2030, PLAYERS, {1: week_one()}, last_regular_season_week=1)
    rows = starts(season)
    assert len(rows) == 8
    by_player = {s.player_id: s for s in rows}
    assert by_player["q1"] == Start(2030, 1, "0001", "q1", "QB", 30.0, 25.0, False)
    assert by_player["q4"].vor == 0.0
    assert by_player["r1"].vor == 9.0
    assert by_player["r4"].vor == 0.0


def test_non_counted_lineups_feed_the_pool_but_yield_no_starts():
    weeks = {
        1: week_one(),
        2: [
            (lineup("0001", {"q1": 12.0}), lineup("0002", {"q2": 30.0})),  # bracket game
            (lineup("0003", {"q3": 8.0}), lineup("0004", {"q4": 2.0})),  # consolation, not counted
        ],
    }
    bracket = (BracketGame(2, "1", 0, "0001", "0002", 1, 2),)
    season = build_season(2030, PLAYERS, weeks, last_regular_season_week=1, bracket=bracket)
    base = baselines(season)
    assert base[(2, "QB")] == 2.0  # q4's consolation start still sets the baseline
    week_two = [s for s in starts(season) if s.week == 2]
    assert {s.player_id for s in week_two} == {"q1", "q2"}
    assert all(s.playoff for s in week_two)
    assert next(s for s in week_two if s.player_id == "q2").vor == 28.0


def test_missing_score_counts_as_zero_points():
    weeks = {1: [(lineup("0001", {"q1": None}), lineup("0002", {"q2": 10.0}))]}
    season = build_season(2030, PLAYERS, weeks, last_regular_season_week=1, franchises=("0001", "0002"))
    rows = {s.player_id: s for s in starts(season)}
    assert rows["q1"].points == 0.0
    assert rows["q1"].vor == 0.0  # two franchises, one QB each: q1 is the 2nd-best, the baseline itself
    assert rows["q2"].vor == 10.0


def test_unknown_position_is_excluded_from_pools_and_worth_zero():
    weeks = {1: [(lineup("0001", {"q1": 20.0, "x1": 50.0}), lineup("0002", {"q2": 10.0}))]}
    season = build_season(2030, PLAYERS, weeks, last_regular_season_week=1, franchises=("0001", "0002"))
    base = baselines(season)
    assert set(base) == {(1, "QB")}
    mystery = next(s for s in starts(season) if s.player_id == "x1")
    assert (mystery.points, mystery.vor) == (50.0, 0.0)
```

- [ ] **Step 3: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_vor.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'hof.stats.vor'`.

- [ ] **Step 4: Implement**

`hof/stats/vor.py`:

```python
"""Value over replacement: each start scored against a weekly positional baseline.

The baseline for a position in a week is the N-th best score among every starter at that
position across every lineup MFL listed that week, where N is the number of franchises times
the position's minimum starters. Fewer than N starters means the lowest score is the baseline.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from hof.model.players import UNKNOWN_POSITION
from hof.model.season import Season

Baselines = dict[tuple[int, str], float]  # (week, position) -> replacement-level score


@dataclass(frozen=True)
class Start:
    year: int
    week: int
    franchise_id: str
    player_id: str
    position: str
    points: float
    vor: float
    playoff: bool


def baselines(season: Season) -> Baselines:
    franchise_count = len(season.franchises)
    result: Baselines = {}
    for week in season.weeks.values():
        pool: dict[str, list[float]] = defaultdict(list)
        for lineup in week.lineups.values():
            if not lineup.played:
                continue
            for player_id in lineup.starters:
                position = season.player(player_id).position
                if position != UNKNOWN_POSITION:
                    pool[position].append(lineup.points(player_id))
        for position, scores in pool.items():
            required = franchise_count * season.starter_minimums.get(position, 1)
            scores.sort(reverse=True)
            result[(week.number, position)] = scores[required - 1] if len(scores) >= required else scores[-1]
    return result


def starts(season: Season, base: Baselines | None = None) -> list[Start]:
    """One row per starter in every counted game, in week order."""
    base = baselines(season) if base is None else base
    rows: list[Start] = []
    for game in season.games():
        for lineup in (game.home, game.away):
            for player_id in lineup.starters:
                position = season.player(player_id).position
                points = lineup.points(player_id)
                if position == UNKNOWN_POSITION:
                    value = 0.0
                else:
                    value = round(points - base.get((game.week, position), 0.0), 1)
                rows.append(Start(season.year, game.week, lineup.franchise_id, player_id, position, points, value, game.playoff))
    return rows
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/hof/test_hof_vor.py -v`
Expected: 5 passed.

- [ ] **Step 6: Lint, run everything, commit**

Run: `ruff check src tests scripts hof && pytest`
Expected: no lint issues; every test passes.

```bash
git add hof/stats/vor.py tests/hof/synthetic.py tests/hof/test_hof_vor.py
git commit -m "feat(hof): value over replacement per start

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: Backfill every season

**Files:**
- Create: `data/raw/2016/` through `data/raw/2026/` (fetched, about 6 MB)

- [ ] **Step 1: Run the backfill (real network, about 300 requests at one per second)**

```bash
python -m hof fetch
```

Expected: log lines `fetching season 2016 from league 79873`, then 2017 through 2026 from 65522, ending with `fetched 11 season(s): [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]`. Takes five to six minutes. If MFL throttles (an `MflThrottled` error), wait ten minutes and rerun; completed seasons are skipped, so only the interrupted one repeats.

- [ ] **Step 2: Smoke-test the loader across all seasons**

```bash
python - <<'EOF'
from pathlib import Path
from hof.snapshots import load_all
from hof.stats.vor import starts
for season in load_all(Path("data")):
    games = season.games()
    print(f"{season.year} league={season.league_id} franchises={len(season.franchises)} weeks={len(season.weeks)} games={len(games)} starts={len(starts(season))} champion={season.champion_id} complete={season.complete}")
EOF
```

Expected: eleven lines. 2016 shows `league=79873`. Every season through 2025 shows `complete=True`, 12 franchises, roughly 80 to 90 games, and a champion id. 2026 shows `complete=False`, a handful of games, and `champion=None`. A `None` champion on a completed season means the bracket did not match the weekly results; inspect that year's `playoffBracket-1.json` and `weeklyResults/W1x.json` before continuing, and record the finding for Plan 2.

- [ ] **Step 3: Commit the snapshots**

```bash
git add data/raw
git commit -m "data: backfill MFL snapshots for 2016 through 2026

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
du -sh data/raw
```

Expected: a single commit around 6 MB.

- [ ] **Step 4: Update the README**

Append a short section to `README.md` after "Development":

```markdown
## Hall of Records (in progress)

`hof/` fetches every BDFL season from MFL into `data/raw/<year>/` and will build the records site. Design: `docs/superpowers/specs/2026-09-06-hall-of-records-design.md`.

```bash
python -m hof fetch            # refresh the current season; completed seasons are skipped
python -m hof fetch --year 2024   # refetch one season (delete data/raw/2024 first if it is marked complete)
```
```

```bash
git add README.md
git commit -m "docs: mention the hall of records fetch command

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Later plans (outlines only; each is written after the previous one ships)

### Plan 2: Stats

Pure functions over `list[Season]` and `list[Start]`, all in `hof/stats/`, each with synthetic-league tests via `build_season`:

1. `careers.py`: stints from weekly roster membership, per-season rows, career totals, arrivals and departures from the transaction log, titles as a starter.
2. `franchises.py`: current names, eras with `normalize_name`, season rows with finish labels, era and all-time totals, streaks across seasons, head-to-head splits and game logs, all-time top starters per franchise.
3. `records.py`: the records-book table from spec section 6, top ten each, playoff flag.
4. `hall.py`: induction by completed season in order, class years, franchise plaques, watch list from the newest week's rosters.
5. `drafts.py`: hindsight columns, steals and busts, franchise draft rankings.
6. `trades.py`: asset resolution. Future picks resolve through the draft pick comments' `Pick traded from <name>` chain to the original franchise's name that season (MFL's `round1DraftOrder` lists post-trade owners, so it cannot identify original owners); current-year `DP_` picks resolve by round and pick; attribution by effective week from `TransactionLog.effective_week`.
7. `milestones.py`: new top-ten entries, 500-point and 100-start milestones, series firsts, playoff picture, bracket summary for a given completed week.
8. A `hof.stats.model.Model` that computes all of the above once per build and is the single input for plans 3 and 4.

### Plan 3: Site and workflow

1. `site/slugs.py`, templates under `hof/site/templates/`, `static/site.css`, `static/site.js`.
2. `site/build.py` rendering every page from the `Model`, the players search index, deterministic output; `python -m hof build --out dist`.
3. Rendering tests on the synthetic league, including the no-franchise-id assertion.
4. `.github/workflows/hof.yml`: schedule, fetch, data commit, build, Pages deploy; CI runs the new tests. Owner enables Pages.

### Plan 4: Discord

1. `discord/notify.py`: completion rule (lock plus 40 hours and every counted matchup scored), `data/notify-state.json`, posting through `bdfl.discord.DiscordWebhook`.
2. `discord/recap.py` and `discord/wrap.py` embeds with golden tests.
3. `python -m hof notify`; the workflow's gated notify step and state commit. Owner sets the secret and the `HOF_NOTIFY` variable.
