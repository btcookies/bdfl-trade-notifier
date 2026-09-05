# BDFL Discord Notifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the MFL trade and waiver notifier as a single Python 3.13 Lambda that polls MFL every minute and posts rich embeds to a Discord webhook, with zero-touch league-year detection, deployed with AWS SAM.

**Architecture:** One Lambda on an EventBridge Scheduler `rate(1 minute)` fetches trades and blind-bid waivers for the auto-detected league year, dedupes against one DynamoDB table that doubles as an outbox, resolves player names on demand, and posts embeds through a webhook URL stored in SSM. Spec: `docs/superpowers/specs/2026-09-04-discord-notifier-design.md`.

**Tech Stack:** Python 3.13, `requests`, boto3 (provided by Lambda), AWS SAM, DynamoDB, EventBridge Scheduler, SSM Parameter Store, pytest, moto 5, `responses`, ruff, GitHub Actions with OIDC.

---

## Working conventions

- Repo: `/Users/brookstaylor/Documents/coding/bdfl-trade-notifier`, branch `discord-port`. Run every command from the repo root.
- Python: use the project venv. Create it in Task 1 and activate with `source .venv/bin/activate` in every shell.
- Tests import from `src/` via `pythonpath = ["src"]` in `pyproject.toml`, so `from bdfl.models import Trade` works without installing the package.
- Commit after every task with the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Never call the real MFL API from unit tests. Only `scripts/dry_run.py` and the explicit live check in Task 10 touch the network.

## File structure

| Path | Responsibility |
|---|---|
| `pyproject.toml` | project metadata, pytest and ruff configuration |
| `requirements-dev.txt` | test and lint dependencies |
| `src/requirements.txt` | runtime dependency for `sam build` (`requests` only) |
| `src/handler.py` | Lambda entry point; builds the poller once per container and logs one JSON line per run |
| `src/bdfl/models.py` | `LeagueInfo`, `Player`, `Trade`, `WaiverClaim`, `parse_transactions`, keys, referenced player ids |
| `src/bdfl/assets.py` | render asset codes and player labels to text |
| `src/bdfl/messages.py` | build trade embeds, waiver messages, details and summaries, chunking |
| `src/bdfl/discord.py` | `DiscordWebhook.post` with one 429 retry |
| `src/bdfl/mfl.py` | `MflClient`: paced requests, `detect_league`, `transactions`, `players` |
| `src/bdfl/store.py` | `TransactionStore` over the DynamoDB table |
| `src/bdfl/config.py` | `Settings.from_env`, webhook URL from SSM or env |
| `src/bdfl/poller.py` | `Poller.run`: the per-invocation flow, caches, backoff, outbox retries |
| `scripts/dry_run.py` | live MFL fetch, prints what would post, optional `--send` |
| `template.yaml`, `samconfig.toml` | infrastructure |
| `infra/github-oidc.yaml` | one-time deploy role for GitHub Actions |
| `.github/workflows/ci.yml`, `.github/workflows/deploy.yml` | tests on PR, deploy on main |
| `tests/conftest.py` | fake AWS credentials and shared fixtures |
| `tests/test_*.py` | one test module per source module |
| `README.md` | setup, hand-off steps, operations |

---

### Task 1: Scaffold the new layout and remove the old code

**Files:**
- Delete: `get_trades.py`, `get_waivers.py`, `get_close_games.py`, `get_franchises.py`, `get_players.py`, `send_bdfl_messages.py`, `groupme/`, `pymfl/`, `test/`, `serverless.yml`, `package.json`, `package-lock.json`, `requirements.txt`
- Create: `pyproject.toml`, `requirements-dev.txt`, `src/requirements.txt`, `src/bdfl/__init__.py`, `tests/conftest.py`, `.gitignore`

- [ ] **Step 1: Remove the old implementation**

```bash
git rm -r -q get_trades.py get_waivers.py get_close_games.py get_franchises.py get_players.py send_bdfl_messages.py groupme pymfl test serverless.yml package.json package-lock.json requirements.txt
```

Expected: no output; `git status` shows the deletions staged.

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "bdfl-notifier"
version = "2.0.0"
description = "Posts MFL trades and waiver claims to Discord"
requires-python = ">=3.13"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = "-q"

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
ignore = ["E501"]

[tool.ruff.lint.isort]
known-first-party = ["bdfl", "handler"]
```

- [ ] **Step 3: Write the requirements files**

`src/requirements.txt`:

```
requests>=2.32,<3
```

`requirements-dev.txt`:

```
-r src/requirements.txt
boto3>=1.35
pytest>=8.3
moto[dynamodb,ssm]>=5.0
responses>=0.25
ruff>=0.6
```

- [ ] **Step 4: Write `.gitignore`**

```
.aws-sam/
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/
.vscode/
.DS_Store
```

- [ ] **Step 5: Create the package and the shared test fixture**

`src/bdfl/__init__.py` is an empty file.

`tests/conftest.py`:

```python
import os

# moto needs credentials and a region before boto3 creates any client.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
```

- [ ] **Step 6: Create the venv and install dependencies**

```bash
python3.13 -m venv .venv && source .venv/bin/activate && pip install -q -r requirements-dev.txt && python -c "import requests, moto, responses, boto3; print('ok')"
```

Expected: `ok`.

- [ ] **Step 7: Confirm pytest runs with no tests**

```bash
source .venv/bin/activate && pytest
```

Expected: `no tests ran` and exit code 5. That is correct for an empty suite.

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "chore: replace Serverless scaffold with SAM-ready Python layout

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Models and transaction parsing

**Files:**
- Create: `src/bdfl/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_models.py`:

```python
from bdfl.models import (
    LeagueInfo,
    Trade,
    WaiverClaim,
    as_list,
    parse_transactions,
    referenced_player_ids,
)

TRADE = {
    "type": "TRADE",
    "timestamp": "1788400073",
    "franchise": "0011",
    "franchise2": "0005",
    "franchise1_gave_up": "15255,13299,",
    "franchise2_gave_up": "17463,BB_20,FP_0005_2027_3,DP_0_1,",
    "comments": "  deal done ",
    "expires": "1789004756",
    "by_commish": "1",
}

WAIVER = {
    "type": "BBID_WAIVER",
    "timestamp": "1788339600",
    "franchise": "0003",
    "transaction": "15733,|3.00|",
}

WAIVER_WITH_DROP = {
    "type": "BBID_WAIVER",
    "timestamp": "1788339600",
    "franchise": "0006",
    "transaction": "14209,|10.00|11247,",
}


def test_as_list_normalizes_none_dict_and_list():
    assert as_list(None) == []
    assert as_list({"a": 1}) == [{"a": 1}]
    assert as_list([1, 2]) == [1, 2]


def test_parse_trade():
    [trade] = parse_transactions({"transactions": {"transaction": [TRADE]}})
    assert isinstance(trade, Trade)
    assert trade.timestamp == 1788400073
    assert trade.franchise1 == "0011"
    assert trade.franchise2 == "0005"
    assert trade.gave_up1 == ("15255", "13299")
    assert trade.gave_up2 == ("17463", "BB_20", "FP_0005_2027_3", "DP_0_1")
    assert trade.comments == "deal done"
    assert trade.raw == TRADE
    assert trade.type == "TRADE"
    assert trade.key == "TRADE#1788400073#0011#0005"
    assert trade.franchise_ids == ["0011", "0005"]


def test_parse_waiver_without_drop():
    [claim] = parse_transactions({"transactions": {"transaction": [WAIVER]}})
    assert isinstance(claim, WaiverClaim)
    assert claim.parsed is True
    assert claim.timestamp == 1788339600
    assert claim.franchise == "0003"
    assert claim.added == "15733"
    assert claim.bid == "3.00"
    assert claim.dropped is None
    assert claim.type == "BBID_WAIVER"
    assert claim.key == "WAIVER#1788339600#0003#15733"
    assert claim.franchise_ids == ["0003"]


def test_parse_waiver_with_drop_and_trailing_comma():
    [claim] = parse_transactions({"transactions": {"transaction": [WAIVER_WITH_DROP]}})
    assert claim.added == "14209"
    assert claim.bid == "10.00"
    assert claim.dropped == "11247"


def test_parse_waiver_unparsable_is_kept_with_stable_key():
    bad = {**WAIVER, "transaction": "garbage"}
    [claim] = parse_transactions({"transactions": {"transaction": [bad]}})
    assert claim.parsed is False
    assert claim.added == ""
    assert claim.key.startswith("WAIVER#1788339600#0003#unparsed-")
    again = parse_transactions({"transactions": {"transaction": [bad]}})[0]
    assert again.key == claim.key


def test_parse_single_transaction_dict_and_ignores_other_types():
    payload = {"transactions": {"transaction": {**TRADE, "type": "IR"}}}
    assert parse_transactions(payload) == []
    payload = {"transactions": {"transaction": TRADE}}
    assert len(parse_transactions(payload)) == 1


def test_parse_empty_payloads():
    assert parse_transactions({}) == []
    assert parse_transactions({"transactions": {}}) == []
    assert parse_transactions({"transactions": {"transaction": []}}) == []


def test_referenced_player_ids_collects_only_numeric_codes_and_claim_players():
    records = parse_transactions(
        {"transactions": {"transaction": [TRADE, WAIVER, WAIVER_WITH_DROP]}}
    )
    assert referenced_player_ids(records) == {
        "15255", "13299", "17463", "15733", "14209", "11247"
    }


def test_league_info_franchise_name_fallback():
    league = LeagueInfo(year=2026, name="BDFL", franchises={"0001": "The Youth Academy"})
    assert league.franchise_name("0001") == "The Youth Academy"
    assert league.franchise_name("0099") == "Franchise 0099"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'bdfl.models'`.

- [ ] **Step 3: Write `src/bdfl/models.py`**

```python
"""Data types for league info, players, and MFL transactions."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

WAIVER_RE = re.compile(r"(\d+),\|([\d.]+)\|(\d*),?")


def as_list(value: Any) -> list:
    """MFL returns a dict instead of a one-element list; normalize to a list."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def split_assets(value: str | None) -> tuple[str, ...]:
    return tuple(code for code in (value or "").split(",") if code)


@dataclass(frozen=True)
class LeagueInfo:
    year: int
    name: str
    franchises: dict[str, str] = field(default_factory=dict)

    def franchise_name(self, franchise_id: str) -> str:
        return self.franchises.get(franchise_id, f"Franchise {franchise_id}")


@dataclass(frozen=True)
class Player:
    id: str
    name: str
    team: str = ""
    position: str = ""


@dataclass(frozen=True)
class Trade:
    timestamp: int
    franchise1: str
    franchise2: str
    gave_up1: tuple[str, ...]
    gave_up2: tuple[str, ...]
    comments: str
    raw: dict

    type = "TRADE"

    @property
    def key(self) -> str:
        return f"TRADE#{self.timestamp}#{self.franchise1}#{self.franchise2}"

    @property
    def franchise_ids(self) -> list[str]:
        return [self.franchise1, self.franchise2]


@dataclass(frozen=True)
class WaiverClaim:
    timestamp: int
    franchise: str
    added: str
    bid: str
    dropped: str | None
    parsed: bool
    raw: dict

    type = "BBID_WAIVER"

    @property
    def key(self) -> str:
        if self.parsed:
            return f"WAIVER#{self.timestamp}#{self.franchise}#{self.added}"
        digest = hashlib.sha1(str(self.raw.get("transaction", "")).encode()).hexdigest()[:8]
        return f"WAIVER#{self.timestamp}#{self.franchise}#unparsed-{digest}"

    @property
    def franchise_ids(self) -> list[str]:
        return [self.franchise]


Record = Trade | WaiverClaim


def parse_transactions(payload: dict) -> list[Record]:
    raw_list = as_list((payload.get("transactions") or {}).get("transaction"))
    records: list[Record] = []
    for raw in raw_list:
        kind = raw.get("type")
        if kind == "TRADE":
            records.append(_parse_trade(raw))
        elif kind == "BBID_WAIVER":
            records.append(_parse_waiver(raw))
    return records


def _parse_trade(raw: dict) -> Trade:
    return Trade(
        timestamp=int(raw["timestamp"]),
        franchise1=raw["franchise"],
        franchise2=raw["franchise2"],
        gave_up1=split_assets(raw.get("franchise1_gave_up")),
        gave_up2=split_assets(raw.get("franchise2_gave_up")),
        comments=(raw.get("comments") or "").strip(),
        raw=raw,
    )


def _parse_waiver(raw: dict) -> WaiverClaim:
    timestamp = int(raw["timestamp"])
    franchise = raw["franchise"]
    match = WAIVER_RE.fullmatch(raw.get("transaction") or "")
    if not match:
        return WaiverClaim(timestamp, franchise, "", "", None, False, raw)
    return WaiverClaim(
        timestamp=timestamp,
        franchise=franchise,
        added=match.group(1),
        bid=match.group(2),
        dropped=match.group(3) or None,
        parsed=True,
        raw=raw,
    )


def referenced_player_ids(records: list[Record]) -> set[str]:
    ids: set[str] = set()
    for record in records:
        if isinstance(record, Trade):
            ids.update(code for code in record.gave_up1 + record.gave_up2 if code.isdigit())
        elif record.parsed:
            ids.add(record.added)
            if record.dropped:
                ids.add(record.dropped)
    return ids
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
source .venv/bin/activate && pytest tests/test_models.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/bdfl/models.py tests/test_models.py && git commit -m "feat: parse MFL trades and waiver claims into records

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Asset and player rendering

**Files:**
- Create: `src/bdfl/assets.py`
- Test: `tests/test_assets.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_assets.py`:

```python
import logging

from bdfl.assets import format_dollars, format_player_name, player_label, render_asset
from bdfl.models import LeagueInfo, Player

LEAGUE = LeagueInfo(year=2026, name="BDFL", franchises={"0005": "Jeff Janis Fan Club"})
PLAYERS = {
    "13299": Player(id="13299", name="Kittle, George", team="SFO", position="TE"),
    "17463": Player(id="17463", name="Simpson, Ty", team="", position="QB"),
    "0151": Player(id="0151", name="Bills, Buffalo", team="BUF", position="TMWR"),
}


def test_format_player_name_swaps_last_first():
    assert format_player_name("Kittle, George") == "George Kittle"
    assert format_player_name("Bills, Buffalo") == "Buffalo Bills"
    assert format_player_name("Madonna") == "Madonna"


def test_player_label_with_and_without_team():
    assert player_label(PLAYERS["13299"], "13299") == "George Kittle, SFO TE"
    assert player_label(PLAYERS["17463"], "17463") == "Ty Simpson, QB"
    assert player_label(None, "999") == "Unknown player (#999)"


def test_format_dollars():
    assert format_dollars("20") == "$20"
    assert format_dollars("3.00") == "$3"
    assert format_dollars("3.50") == "$3.50"
    assert format_dollars("abc") == "$abc"


def test_render_player_asset():
    assert render_asset("13299", LEAGUE, PLAYERS) == "George Kittle, SFO TE"
    assert render_asset("424242", LEAGUE, PLAYERS) == "Unknown player (#424242)"


def test_render_blind_bid_dollars():
    assert render_asset("BB_20", LEAGUE, PLAYERS) == "$20 blind bid dollars"


def test_render_future_pick_uses_franchise_name_and_one_based_round():
    assert render_asset("FP_0005_2027_3", LEAGUE, PLAYERS) == "Jeff Janis Fan Club 2027 Round 3 pick"
    assert render_asset("FP_0099_2027_1", LEAGUE, PLAYERS) == "Franchise 0099 2027 Round 1 pick"


def test_render_current_pick_is_zero_based_in_mfl():
    assert render_asset("DP_2_5", LEAGUE, PLAYERS) == "2026 Round 3 Pick 6"
    assert render_asset("DP_0_0", LEAGUE, PLAYERS) == "2026 Round 1 Pick 1"


def test_render_unknown_code_returns_raw_and_warns(caplog):
    with caplog.at_level(logging.WARNING):
        assert render_asset("XX_1", LEAGUE, PLAYERS) == "XX_1"
        assert render_asset("DP_a_b", LEAGUE, PLAYERS) == "DP_a_b"
    assert "unknown asset code" in caplog.text
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_assets.py -v
```

Expected: `ModuleNotFoundError: No module named 'bdfl.assets'`.

- [ ] **Step 3: Write `src/bdfl/assets.py`**

```python
"""Render MFL asset codes and players as human-readable text."""

from __future__ import annotations

import logging

from bdfl.models import LeagueInfo, Player

log = logging.getLogger(__name__)


def format_player_name(name: str) -> str:
    """MFL gives 'Last, First'; return 'First Last'."""
    if "," in name:
        last, first = name.split(",", 1)
        return f"{first.strip()} {last.strip()}".strip()
    return name.strip()


def player_label(player: Player | None, player_id: str) -> str:
    if player is None:
        return f"Unknown player (#{player_id})"
    name = format_player_name(player.name)
    tag = " ".join(part for part in (player.team, player.position) if part)
    return f"{name}, {tag}" if tag else name


def format_dollars(amount: str) -> str:
    try:
        value = float(amount)
    except ValueError:
        return f"${amount}"
    return f"${int(value)}" if value == int(value) else f"${value:.2f}"


def render_asset(code: str, league: LeagueInfo, players: dict[str, Player]) -> str:
    if code.isdigit():
        return player_label(players.get(code), code)
    parts = code.split("_")
    if parts[0] == "BB" and len(parts) == 2:
        return f"{format_dollars(parts[1])} blind bid dollars"
    if parts[0] == "FP" and len(parts) == 4:
        _, franchise_id, year, rnd = parts
        return f"{league.franchise_name(franchise_id)} {year} Round {rnd} pick"
    if parts[0] == "DP" and len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
        # MFL encodes current-year picks zero-based: DP_2_5 is round 3, pick 6.
        return f"{league.year} Round {int(parts[1]) + 1} Pick {int(parts[2]) + 1}"
    log.warning("unknown asset code %s", code)
    return code
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
source .venv/bin/activate && pytest tests/test_assets.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/bdfl/assets.py tests/test_assets.py && git commit -m "feat: render asset codes with correct zero-based draft picks

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Discord embeds, details, summaries, and chunking

**Files:**
- Create: `src/bdfl/messages.py`
- Test: `tests/test_messages.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_messages.py`:

```python
from bdfl.messages import (
    MAX_DESCRIPTION,
    chunk_entries,
    trade_details,
    trade_embed,
    trade_summary,
    waiver_details,
    waiver_messages,
    waiver_summary,
)
from bdfl.models import LeagueInfo, Player, Trade, WaiverClaim

LEAGUE = LeagueInfo(
    year=2026,
    name="Barbara Dodson's Fantasy League",
    franchises={"0011": "A.J. Mudbone", "0005": "Jeff Janis Fan Club", "0003": "The Youth Academy"},
)
PLAYERS = {
    "13299": Player("13299", "Kittle, George", "SFO", "TE"),
    "15255": Player("15255", "Gainwell, Kenneth", "TBB", "RB"),
    "15733": Player("15733", "Doe, John", "NYG", "WR"),
    "11247": Player("11247", "Ertz, Zach", "PHI", "TE"),
}


def make_trade(comments=""):
    return Trade(
        timestamp=1788400073,
        franchise1="0011",
        franchise2="0005",
        gave_up1=("15255", "13299"),
        gave_up2=("BB_20", "FP_0005_2027_3"),
        comments=comments,
        raw={},
    )


def make_claim(franchise="0003", added="15733", dropped=None, timestamp=1788339600, parsed=True):
    return WaiverClaim(
        timestamp=timestamp,
        franchise=franchise,
        added=added,
        bid="3.00",
        dropped=dropped,
        parsed=parsed,
        raw={"transaction": "garbage"},
    )


def test_trade_details_and_summary():
    details = trade_details(make_trade("Go Birds"), LEAGUE, PLAYERS)
    assert details == {
        "sides": [
            {
                "franchise_id": "0011",
                "franchise_name": "A.J. Mudbone",
                "assets": ["Kenneth Gainwell, TBB RB", "George Kittle, SFO TE"],
            },
            {
                "franchise_id": "0005",
                "franchise_name": "Jeff Janis Fan Club",
                "assets": ["$20 blind bid dollars", "Jeff Janis Fan Club 2027 Round 3 pick"],
            },
        ],
        "comments": "Go Birds",
    }
    assert trade_summary(details) == (
        "A.J. Mudbone gives up: Kenneth Gainwell, TBB RB, George Kittle, SFO TE | "
        "Jeff Janis Fan Club gives up: $20 blind bid dollars, Jeff Janis Fan Club 2027 Round 3 pick"
    )


def test_trade_embed_layout():
    trade = make_trade("Go Birds")
    embed = trade_embed(trade, trade_details(trade, LEAGUE, PLAYERS), LEAGUE)
    assert embed == {
        "title": "🚨 Trade Completed",
        "color": 0xE74C3C,
        "description": "Go Birds",
        "fields": [
            {
                "name": "A.J. Mudbone gives up",
                "value": "• Kenneth Gainwell, TBB RB\n• George Kittle, SFO TE",
                "inline": False,
            },
            {
                "name": "Jeff Janis Fan Club gives up",
                "value": "• $20 blind bid dollars\n• Jeff Janis Fan Club 2027 Round 3 pick",
                "inline": False,
            },
        ],
        "footer": {"text": "MFL · Barbara Dodson's Fantasy League · 2026"},
        "timestamp": "2026-09-03T01:47:53+00:00",
    }


def test_trade_embed_without_comments_and_with_empty_side():
    trade = Trade(1788400073, "0011", "0005", (), ("13299",), "", {})
    embed = trade_embed(trade, trade_details(trade, LEAGUE, PLAYERS), LEAGUE)
    assert "description" not in embed
    assert embed["fields"][0]["value"] == "• (nothing)"


def test_trade_embed_truncates_long_comments():
    trade = make_trade("x" * 2000)
    embed = trade_embed(trade, trade_details(trade, LEAGUE, PLAYERS), LEAGUE)
    assert len(embed["description"]) == 1000
    assert embed["description"].endswith("…")


def test_waiver_details_and_summary():
    details = waiver_details(make_claim(dropped="11247"), LEAGUE, PLAYERS)
    assert details == {
        "franchise_id": "0003",
        "franchise_name": "The Youth Academy",
        "bid": "$3",
        "added": "John Doe, NYG WR",
        "dropped": "Zach Ertz, PHI TE",
    }
    assert waiver_summary(details) == (
        "The Youth Academy won John Doe, NYG WR for $3, dropped Zach Ertz, PHI TE"
    )


def test_unparsed_waiver_details_and_summary():
    details = waiver_details(make_claim(added="", parsed=False), LEAGUE, PLAYERS)
    assert details["added"] is None
    assert details["raw_transaction"] == "garbage"
    assert waiver_summary(details) == "unparsed waiver: The Youth Academy garbage"


def test_waiver_messages_single_embed_sorted_by_time_then_franchise():
    later = make_claim(franchise="0011", added="13299", timestamp=1788339700)
    first = make_claim(franchise="0005", added="15255", dropped="11247")
    second = make_claim(franchise="0003", added="15733")
    items = [(later, waiver_details(later, LEAGUE, PLAYERS)),
             (first, waiver_details(first, LEAGUE, PLAYERS)),
             (second, waiver_details(second, LEAGUE, PLAYERS))]
    [(embeds, claims)] = waiver_messages(items, LEAGUE)
    assert claims == [first, second, later]
    assert embeds == [{
        "title": "✅ Waiver Claims Processed",
        "color": 0x2ECC71,
        "description": (
            "**Jeff Janis Fan Club** won **Kenneth Gainwell, TBB RB** for $3 · dropped Zach Ertz, PHI TE\n"
            "**The Youth Academy** won **John Doe, NYG WR** for $3\n"
            "**A.J. Mudbone** won **George Kittle, SFO TE** for $3"
        ),
        "footer": {"text": "MFL · Barbara Dodson's Fantasy League · 2026"},
        "timestamp": "2026-09-02T09:01:40+00:00",
    }]


def test_waiver_messages_unparsed_line():
    claim = make_claim(added="", parsed=False)
    [(embeds, _)] = waiver_messages([(claim, waiver_details(claim, LEAGUE, PLAYERS))], LEAGUE)
    assert embeds[0]["description"] == "**The Youth Academy** claim could not be parsed: `garbage`"


def test_waiver_messages_split_across_embeds_and_messages():
    # Each line is ~54 chars, so ~75 fit per 4096-char embed; 1200 claims need 16 embeds,
    # which is more than the 10 allowed per message, so two messages.
    items = []
    for i in range(1200):
        claim = make_claim(added="15733", timestamp=1788339600 + i)
        items.append((claim, waiver_details(claim, LEAGUE, PLAYERS)))
    messages = waiver_messages(items, LEAGUE)
    assert len(messages) == 2
    assert len(messages[0][0]) == 10
    assert all(len(e["description"]) <= MAX_DESCRIPTION for embeds, _ in messages for e in embeds)
    assert messages[0][0][0]["title"].startswith("✅ Waiver Claims Processed (1/")
    assert sum(len(claims) for _, claims in messages) == 1200
    assert [c for _, claims in messages for c in claims] == [c for c, _ in items]


def test_chunk_entries_respects_limit_and_newlines():
    entries = [("a", "xxxx"), ("b", "yyyy"), ("c", "zz")]
    assert chunk_entries(entries, limit=9) == [[("a", "xxxx"), ("b", "yyyy")], [("c", "zz")]]
    assert chunk_entries(entries, limit=8) == [[("a", "xxxx")], [("b", "yyyy"), ("c", "zz")]]
    assert chunk_entries([], limit=9) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_messages.py -v
```

Expected: `ModuleNotFoundError: No module named 'bdfl.messages'`.

- [ ] **Step 3: Write `src/bdfl/messages.py`**

```python
"""Build Discord embeds, stored details, and summaries for trades and waiver claims."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypeVar

from bdfl.assets import format_dollars, player_label, render_asset
from bdfl.models import LeagueInfo, Player, Trade, WaiverClaim

TRADE_COLOR = 0xE74C3C
WAIVER_COLOR = 0x2ECC71
MAX_EMBEDS_PER_MESSAGE = 10
MAX_TITLE = 256
MAX_DESCRIPTION = 4096
MAX_FIELD_VALUE = 1024
MAX_COMMENTS = 1000

T = TypeVar("T")


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def iso_timestamp(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat()


def footer(league: LeagueInfo) -> dict:
    return {"text": f"MFL · {league.name} · {league.year}"}


# --- trades -----------------------------------------------------------------


def trade_details(trade: Trade, league: LeagueInfo, players: dict[str, Player]) -> dict:
    sides = []
    for franchise_id, codes in ((trade.franchise1, trade.gave_up1), (trade.franchise2, trade.gave_up2)):
        sides.append(
            {
                "franchise_id": franchise_id,
                "franchise_name": league.franchise_name(franchise_id),
                "assets": [render_asset(code, league, players) for code in codes],
            }
        )
    return {"sides": sides, "comments": trade.comments}


def trade_summary(details: dict) -> str:
    return " | ".join(
        f"{side['franchise_name']} gives up: {', '.join(side['assets']) or 'nothing'}"
        for side in details["sides"]
    )


def trade_embed(trade: Trade, details: dict, league: LeagueInfo) -> dict:
    fields = []
    for side in details["sides"]:
        bullets = "\n".join(f"• {asset}" for asset in side["assets"]) or "• (nothing)"
        fields.append(
            {
                "name": truncate(f"{side['franchise_name']} gives up", MAX_TITLE),
                "value": truncate(bullets, MAX_FIELD_VALUE),
                "inline": False,
            }
        )
    embed = {
        "title": "🚨 Trade Completed",
        "color": TRADE_COLOR,
        "fields": fields,
        "footer": footer(league),
        "timestamp": iso_timestamp(trade.timestamp),
    }
    if details["comments"]:
        embed["description"] = truncate(details["comments"], MAX_COMMENTS)
    return embed


# --- waivers ----------------------------------------------------------------


def waiver_details(claim: WaiverClaim, league: LeagueInfo, players: dict[str, Player]) -> dict:
    base = {"franchise_id": claim.franchise, "franchise_name": league.franchise_name(claim.franchise)}
    if not claim.parsed:
        return {
            **base,
            "bid": "",
            "added": None,
            "dropped": None,
            "raw_transaction": str(claim.raw.get("transaction", "")),
        }
    return {
        **base,
        "bid": format_dollars(claim.bid),
        "added": player_label(players.get(claim.added), claim.added),
        "dropped": player_label(players.get(claim.dropped), claim.dropped) if claim.dropped else None,
    }


def waiver_summary(details: dict) -> str:
    if details["added"] is None:
        return f"unparsed waiver: {details['franchise_name']} {details['raw_transaction']}"
    text = f"{details['franchise_name']} won {details['added']} for {details['bid']}"
    if details["dropped"]:
        text += f", dropped {details['dropped']}"
    return text


def waiver_line(details: dict) -> str:
    if details["added"] is None:
        return f"**{details['franchise_name']}** claim could not be parsed: `{details['raw_transaction']}`"
    line = f"**{details['franchise_name']}** won **{details['added']}** for {details['bid']}"
    if details["dropped"]:
        line += f" · dropped {details['dropped']}"
    return line


def chunk_entries(entries: list[tuple[T, str]], limit: int) -> list[list[tuple[T, str]]]:
    """Group (item, text) entries so each group's texts joined by newlines fit in limit."""
    chunks: list[list[tuple[T, str]]] = []
    size = 0
    for item, text in entries:
        needed = len(text) + (1 if chunks and chunks[-1] else 0)
        if not chunks or size + needed > limit:
            chunks.append([])
            size = 0
            needed = len(text)
        chunks[-1].append((item, text))
        size += needed
    return chunks


def waiver_messages(
    items: list[tuple[WaiverClaim, dict]], league: LeagueInfo
) -> list[tuple[list[dict], list[WaiverClaim]]]:
    """Return (embeds, claims) per Discord message, in posting order."""
    if not items:
        return []
    ordered = sorted(items, key=lambda pair: (pair[0].timestamp, pair[1]["franchise_name"]))
    entries = [(claim, truncate(waiver_line(details), MAX_DESCRIPTION)) for claim, details in ordered]
    chunks = chunk_entries(entries, MAX_DESCRIPTION)
    latest = max(claim.timestamp for claim, _ in ordered)
    embeds: list[tuple[dict, list[WaiverClaim]]] = []
    for index, chunk in enumerate(chunks):
        title = "✅ Waiver Claims Processed"
        if len(chunks) > 1:
            title += f" ({index + 1}/{len(chunks)})"
        embed = {
            "title": title,
            "color": WAIVER_COLOR,
            "description": "\n".join(text for _, text in chunk),
            "footer": footer(league),
            "timestamp": iso_timestamp(latest),
        }
        embeds.append((embed, [claim for claim, _ in chunk]))
    messages = []
    for start in range(0, len(embeds), MAX_EMBEDS_PER_MESSAGE):
        group = embeds[start : start + MAX_EMBEDS_PER_MESSAGE]
        messages.append(([embed for embed, _ in group], [c for _, claims in group for c in claims]))
    return messages
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
source .venv/bin/activate && pytest tests/test_messages.py -v
```

Expected: 10 passed. If the two ISO timestamps differ, compute the expected values with `python -c "from datetime import datetime, UTC; print(datetime.fromtimestamp(1788400073, tz=UTC).isoformat())"` and fix the test constant, not the code.

- [ ] **Step 5: Commit**

```bash
git add src/bdfl/messages.py tests/test_messages.py && git commit -m "feat: build Discord embeds for trades and waiver batches

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Discord webhook client

**Files:**
- Create: `src/bdfl/discord.py`
- Test: `tests/test_discord.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_discord.py`:

```python
import json

import pytest
import responses

from bdfl.discord import DiscordError, DiscordWebhook

URL = "https://discord.com/api/webhooks/123/abc"
EMBED = {"title": "hi"}


@responses.activate
def test_post_sends_embeds_with_username_and_no_mentions():
    responses.post(URL, json={"id": "1"}, status=200)
    DiscordWebhook(URL, sleep=lambda s: None).post([EMBED])
    call = responses.calls[0]
    assert call.request.url == URL + "?wait=true"
    body = json.loads(call.request.body)
    assert body == {"username": "BDFL", "embeds": [EMBED], "allowed_mentions": {"parse": []}}


@responses.activate
def test_post_retries_once_after_429_using_retry_after_capped_at_five_seconds():
    responses.post(URL, json={"retry_after": 30}, status=429, headers={"Retry-After": "30"})
    responses.post(URL, json={"id": "1"}, status=200)
    slept = []
    DiscordWebhook(URL, sleep=slept.append).post([EMBED])
    assert slept == [5.0]
    assert len(responses.calls) == 2


@responses.activate
def test_post_raises_after_second_429():
    responses.post(URL, status=429, headers={"Retry-After": "1"})
    responses.post(URL, status=429, headers={"Retry-After": "1"})
    with pytest.raises(DiscordError):
        DiscordWebhook(URL, sleep=lambda s: None).post([EMBED])


@responses.activate
def test_post_raises_on_server_error_without_retry():
    responses.post(URL, status=502, body="bad gateway")
    with pytest.raises(DiscordError, match="502"):
        DiscordWebhook(URL, sleep=lambda s: None).post([EMBED])
    assert len(responses.calls) == 1


@responses.activate
def test_post_wraps_connection_errors():
    responses.post(URL, body=ConnectionError("boom"))
    with pytest.raises(DiscordError):
        DiscordWebhook(URL, sleep=lambda s: None).post([EMBED])
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_discord.py -v
```

Expected: `ModuleNotFoundError: No module named 'bdfl.discord'`.

- [ ] **Step 3: Write `src/bdfl/discord.py`**

```python
"""Minimal Discord webhook client."""

from __future__ import annotations

import time
from collections.abc import Callable

import requests

MAX_RETRY_AFTER_SECONDS = 5.0


class DiscordError(Exception):
    pass


class DiscordWebhook:
    def __init__(
        self,
        url: str,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        username: str = "BDFL",
        timeout: float = 10.0,
    ):
        self.url = url
        self.session = session or requests.Session()
        self.sleep = sleep
        self.username = username
        self.timeout = timeout

    def post(self, embeds: list[dict]) -> None:
        body = {"username": self.username, "embeds": embeds, "allowed_mentions": {"parse": []}}
        response = self._send(body)
        if response.status_code == 429:
            self.sleep(self._retry_after(response))
            response = self._send(body)
        if not 200 <= response.status_code < 300:
            raise DiscordError(f"Discord webhook returned {response.status_code}: {response.text[:200]}")

    def _send(self, body: dict) -> requests.Response:
        try:
            return self.session.post(
                self.url, params={"wait": "true"}, json=body, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise DiscordError(f"Discord request failed: {exc}") from exc

    @staticmethod
    def _retry_after(response: requests.Response) -> float:
        raw = response.headers.get("Retry-After", "1")
        try:
            seconds = float(raw)
        except ValueError:
            seconds = 1.0
        return min(max(seconds, 0.0), MAX_RETRY_AFTER_SECONDS)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
source .venv/bin/activate && pytest tests/test_discord.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/bdfl/discord.py tests/test_discord.py && git commit -m "feat: add Discord webhook client with single 429 retry

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: MFL client with pacing, year detection, transactions, and players

**Files:**
- Create: `src/bdfl/mfl.py`
- Test: `tests/test_mfl.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_mfl.py`:

```python
from datetime import UTC, datetime

import pytest
import responses

from bdfl.mfl import BASE_URL, LeagueNotFound, MflClient, MflError, MflThrottled

LEAGUE_ID = "65522"
NOW = datetime(2026, 9, 4, tzinfo=UTC)


def league_body(year, years, franchises=None):
    return {
        "league": {
            "id": LEAGUE_ID,
            "name": "BDFL",
            "history": {"league": [{"year": str(y), "url": f"https://x/{y}"} for y in years]},
            "franchises": {
                "franchise": franchises
                or [{"id": "0001", "name": "The Youth Academy"}, {"id": "0002", "name": "A.J. Mudbone"}]
            },
        }
    }


def make_client(**kwargs):
    defaults = {"league_id": LEAGUE_ID, "user_agent": "test-agent", "sleep": lambda s: None}
    return MflClient(**{**defaults, **kwargs})


@responses.activate
def test_detect_league_uses_current_year_when_it_exists():
    responses.get(
        f"{BASE_URL}/2026/export", json=league_body(2026, [2026, 2016, 2025]), match=[
            responses.matchers.query_param_matcher({"TYPE": "league", "L": LEAGUE_ID, "JSON": "1"})
        ]
    )
    league = make_client().detect_league(NOW)
    assert league.year == 2026
    assert league.name == "BDFL"
    assert league.franchises == {"0001": "The Youth Academy", "0002": "A.J. Mudbone"}
    assert responses.calls[0].request.headers["User-Agent"] == "test-agent"


@responses.activate
def test_detect_league_falls_back_to_prior_year_on_404_and_reads_newer_year_from_history():
    responses.get(f"{BASE_URL}/2026/export", status=404, body="<H1>Not Found</H1>")
    responses.get(f"{BASE_URL}/2025/export", json=league_body(2025, [2025, 2024]))
    assert make_client().detect_league(NOW).year == 2025

    responses.reset()
    responses.get(f"{BASE_URL}/2026/export", json={"error": {"$t": "Invalid league ID"}})
    responses.get(f"{BASE_URL}/2025/export", json=league_body(2025, [2025, 2026]))
    responses.get(f"{BASE_URL}/2026/export", json=league_body(2026, [2025, 2026],
                  franchises=[{"id": "0001", "name": "Renamed"}]))
    league = make_client().detect_league(NOW)
    assert league.year == 2026
    assert league.franchises == {"0001": "Renamed"}


@responses.activate
def test_detect_league_handles_single_history_entry_dict():
    body = league_body(2026, [2026])
    body["league"]["history"]["league"] = body["league"]["history"]["league"][0]
    responses.get(f"{BASE_URL}/2026/export", json=body)
    assert make_client().detect_league(NOW).year == 2026


@responses.activate
def test_detect_league_raises_when_no_year_exists():
    responses.get(f"{BASE_URL}/2026/export", status=404)
    responses.get(f"{BASE_URL}/2025/export", status=404)
    with pytest.raises(LeagueNotFound):
        make_client().detect_league(NOW)


@responses.activate
def test_transactions_passes_types_and_days_and_returns_payload():
    payload = {"transactions": {"transaction": [{"type": "TRADE"}]}}
    responses.get(f"{BASE_URL}/2026/export", json=payload, match=[
        responses.matchers.query_param_matcher({
            "TYPE": "transactions", "L": LEAGUE_ID, "JSON": "1",
            "TRANS_TYPE": "TRADE,BBID_WAIVER", "DAYS": "1",
        })
    ])
    assert make_client().transactions(2026) == payload


@responses.activate
def test_transactions_raises_on_error_body_and_bad_status():
    responses.get(f"{BASE_URL}/2026/export", json={"error": {"$t": "nope"}})
    with pytest.raises(MflError, match="nope"):
        make_client().transactions(2026)
    responses.reset()
    responses.get(f"{BASE_URL}/2026/export", status=500)
    with pytest.raises(MflError, match="500"):
        make_client().transactions(2026)
    responses.reset()
    responses.get(f"{BASE_URL}/2026/export", status=404)
    with pytest.raises(MflError):
        make_client().transactions(2026)


@responses.activate
def test_throttled_raises_specific_error_and_does_not_retry():
    responses.get(f"{BASE_URL}/2026/export", status=429)
    with pytest.raises(MflThrottled):
        make_client().transactions(2026)
    assert len(responses.calls) == 1


@responses.activate
def test_players_returns_map_and_skips_request_for_no_ids():
    responses.get(f"{BASE_URL}/2026/export", json={"players": {"player": [
        {"id": "13299", "name": "Kittle, George", "team": "SFO", "position": "TE"},
        {"id": "17463", "name": "Simpson, Ty", "position": "QB", "status": "R"},
    ]}}, match=[responses.matchers.query_param_matcher({
        "TYPE": "players", "L": LEAGUE_ID, "JSON": "1", "PLAYERS": "13299,17463",
    })])
    players = make_client().players(2026, ["17463", "13299", "13299"])
    assert players["13299"].name == "Kittle, George"
    assert players["13299"].team == "SFO"
    assert players["17463"].team == ""
    assert make_client().players(2026, []) == {}
    assert len(responses.calls) == 1


@responses.activate
def test_requests_are_paced_one_second_apart():
    responses.get(f"{BASE_URL}/2026/export", json=league_body(2026, [2026]))
    responses.get(f"{BASE_URL}/2026/export", json={"transactions": {}})
    slept = []
    # clock() is read once after each request finishes and once before each paced request:
    # finish of request 1 (100.0), pace check before request 2 (100.3), finish of request 2.
    ticks = iter([100.0, 100.3, 100.3])
    client = make_client(sleep=slept.append, clock=lambda: next(ticks))
    client.detect_league(NOW)
    client.transactions(2026)
    assert slept == [pytest.approx(0.7)]


@responses.activate
def test_non_json_body_raises_mfl_error():
    responses.get(f"{BASE_URL}/2026/export", body="<html>oops</html>", status=200)
    with pytest.raises(MflError, match="JSON"):
        make_client().transactions(2026)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_mfl.py -v
```

Expected: `ModuleNotFoundError: No module named 'bdfl.mfl'`.

- [ ] **Step 3: Write `src/bdfl/mfl.py`**

```python
"""Client for the MyFantasyLeague export API."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from datetime import datetime

import requests

from bdfl.models import LeagueInfo, Player, as_list

BASE_URL = "https://api.myfantasyleague.com"
MIN_SECONDS_BETWEEN_REQUESTS = 1.0
DEFAULT_TYPES = "TRADE,BBID_WAIVER"

log = logging.getLogger(__name__)


class MflError(Exception):
    pass


class MflThrottled(MflError):
    pass


class LeagueNotFound(MflError):
    pass


class MflClient:
    def __init__(
        self,
        league_id: str,
        user_agent: str,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        timeout: float = 10.0,
    ):
        self.league_id = league_id
        self.user_agent = user_agent
        self.session = session or requests.Session()
        self.sleep = sleep
        self.clock = clock
        self.timeout = timeout
        self._last_request_at: float | None = None

    # --- public API ---------------------------------------------------------

    def league(self, year: int) -> dict | None:
        """Return the league element, or None when the year or league does not exist."""
        status, data = self._get(year, {"TYPE": "league"})
        if status != 200 or data is None or "error" in data:
            return None
        return data.get("league")

    def detect_league(self, now: datetime) -> LeagueInfo:
        for year in (now.year, now.year - 1):
            league = self.league(year)
            if league is None:
                continue
            years = {year}
            for entry in as_list((league.get("history") or {}).get("league")):
                value = str(entry.get("year", ""))
                if value.isdigit():
                    years.add(int(value))
            best = max(years)
            if best != year:
                newer = self.league(best)
                if newer is not None:
                    league = newer
                else:
                    best = year
            return LeagueInfo(
                year=best,
                name=str(league.get("name", "")),
                franchises={
                    f["id"]: f.get("name") or f"Franchise {f['id']}"
                    for f in as_list((league.get("franchises") or {}).get("franchise"))
                    if "id" in f
                },
            )
        raise LeagueNotFound(f"league {self.league_id} not found for {now.year} or {now.year - 1}")

    def transactions(self, year: int, days: int = 1, types: str = DEFAULT_TYPES) -> dict:
        status, data = self._get(
            year, {"TYPE": "transactions", "TRANS_TYPE": types, "DAYS": str(days)}
        )
        return self._require_ok(status, data, "transactions")

    def players(self, year: int, ids: Iterable[str]) -> dict[str, Player]:
        wanted = sorted(set(ids))
        if not wanted:
            return {}
        status, data = self._get(year, {"TYPE": "players", "PLAYERS": ",".join(wanted)})
        data = self._require_ok(status, data, "players")
        return {
            p["id"]: Player(
                id=p["id"],
                name=p.get("name", ""),
                team=p.get("team", ""),
                position=p.get("position", ""),
            )
            for p in as_list((data.get("players") or {}).get("player"))
            if "id" in p
        }

    # --- internals ----------------------------------------------------------

    def _require_ok(self, status: int, data: dict | None, what: str) -> dict:
        if status != 200 or data is None:
            raise MflError(f"MFL {what} request returned status {status}")
        if "error" in data:
            raise MflError(f"MFL {what} error: {data['error']}")
        return data

    def _get(self, year: int, params: dict) -> tuple[int, dict | None]:
        self._pace()
        query = {"TYPE": params["TYPE"], "L": self.league_id, "JSON": "1"}
        query.update({k: v for k, v in params.items() if k != "TYPE"})
        try:
            response = self.session.get(
                f"{BASE_URL}/{year}/export",
                params=query,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise MflError(f"MFL request failed: {exc}") from exc
        finally:
            self._last_request_at = self.clock()
        if response.status_code == 429:
            raise MflThrottled(f"MFL throttled TYPE={params['TYPE']} for {year}")
        if response.status_code == 404:
            return 404, None
        if response.status_code != 200:
            raise MflError(f"MFL returned {response.status_code} for TYPE={params['TYPE']}")
        try:
            return 200, response.json()
        except ValueError as exc:
            raise MflError("MFL returned a non-JSON body") from exc

    def _pace(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = self.clock() - self._last_request_at
        if elapsed < MIN_SECONDS_BETWEEN_REQUESTS:
            self.sleep(MIN_SECONDS_BETWEEN_REQUESTS - elapsed)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
source .venv/bin/activate && pytest tests/test_mfl.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/bdfl/mfl.py tests/test_mfl.py && git commit -m "feat: MFL client with year detection, pacing, and throttle handling

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: DynamoDB transaction store

**Files:**
- Create: `src/bdfl/store.py`
- Test: `tests/test_store.py`
- Modify: `tests/conftest.py` (add the table fixture)

- [ ] **Step 1: Add a moto table fixture to `tests/conftest.py`**

Append to `tests/conftest.py`:

```python
import boto3
import pytest
from moto import mock_aws

TABLE_NAME = "bdfl-notifier-transactions"


@pytest.fixture
def dynamodb_table():
    """A moto-backed table with the same key schema as template.yaml."""
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        table = resource.create_table(
            TableName=TABLE_NAME,
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )
        table.wait_until_exists()
        yield resource, TABLE_NAME
```

- [ ] **Step 2: Write the failing tests**

`tests/test_store.py`:

```python
from bdfl.store import TransactionStore


def item(key, state="pending", attempts=0):
    return {
        "pk": key,
        "type": "TRADE",
        "year": 2026,
        "timestamp": 1788400073,
        "franchise_ids": ["0011", "0005"],
        "raw": {"type": "TRADE"},
        "details": {"sides": [], "comments": ""},
        "summary": "x",
        "notify_state": state,
        "notify_attempts": attempts,
        "first_seen_at": 1788400100,
    }


def test_put_new_is_conditional(dynamodb_table):
    resource, name = dynamodb_table
    store = TransactionStore(name, resource=resource)
    assert store.put_new(item("TRADE#1")) is True
    assert store.put_new(item("TRADE#1", state="sent")) is False
    assert store.get_many(["TRADE#1"])["TRADE#1"]["notify_state"] == "pending"


def test_get_many_returns_only_existing_and_handles_more_than_100_keys(dynamodb_table):
    resource, name = dynamodb_table
    store = TransactionStore(name, resource=resource)
    for i in range(120):
        store.put_new(item(f"TRADE#{i}"))
    keys = [f"TRADE#{i}" for i in range(130)]
    found = store.get_many(keys)
    assert len(found) == 120
    assert "TRADE#129" not in found
    assert store.get_many([]) == {}


def test_mark_sent_sets_state_and_timestamp(dynamodb_table):
    resource, name = dynamodb_table
    store = TransactionStore(name, resource=resource)
    store.put_new(item("TRADE#1"))
    store.mark_sent("TRADE#1", at=1788400200)
    row = store.get_many(["TRADE#1"])["TRADE#1"]
    assert row["notify_state"] == "sent"
    assert int(row["notified_at"]) == 1788400200


def test_bump_attempt_increments_and_returns_count(dynamodb_table):
    resource, name = dynamodb_table
    store = TransactionStore(name, resource=resource)
    store.put_new(item("TRADE#1"))
    assert store.bump_attempt("TRADE#1") == 1
    assert store.bump_attempt("TRADE#1") == 2
    assert int(store.get_many(["TRADE#1"])["TRADE#1"]["notify_attempts"]) == 2


def test_mark_failed(dynamodb_table):
    resource, name = dynamodb_table
    store = TransactionStore(name, resource=resource)
    store.put_new(item("TRADE#1"))
    store.mark_failed("TRADE#1")
    assert store.get_many(["TRADE#1"])["TRADE#1"]["notify_state"] == "failed"
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'bdfl.store'`.

- [ ] **Step 4: Write `src/bdfl/store.py`**

```python
"""DynamoDB-backed store that doubles as the notification outbox."""

from __future__ import annotations

import boto3
from botocore.exceptions import ClientError

BATCH_GET_LIMIT = 100
MAX_UNPROCESSED_ROUNDS = 5


class TransactionStore:
    def __init__(self, table_name: str, resource=None):
        self.resource = resource or boto3.resource("dynamodb")
        self.table_name = table_name
        self.table = self.resource.Table(table_name)

    def get_many(self, keys: list[str]) -> dict[str, dict]:
        found: dict[str, dict] = {}
        for start in range(0, len(keys), BATCH_GET_LIMIT):
            request = {self.table_name: {"Keys": [{"pk": k} for k in keys[start : start + BATCH_GET_LIMIT]]}}
            for _ in range(MAX_UNPROCESSED_ROUNDS):
                response = self.resource.batch_get_item(RequestItems=request)
                for row in response.get("Responses", {}).get(self.table_name, []):
                    found[row["pk"]] = row
                request = response.get("UnprocessedKeys") or {}
                if not request.get(self.table_name):
                    break
        return found

    def put_new(self, item: dict) -> bool:
        """Insert only if the key is absent. Returns False when it already exists."""
        try:
            self.table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def mark_sent(self, key: str, at: int) -> None:
        self.table.update_item(
            Key={"pk": key},
            UpdateExpression="SET notify_state = :state, notified_at = :at",
            ExpressionAttributeValues={":state": "sent", ":at": at},
        )

    def bump_attempt(self, key: str) -> int:
        response = self.table.update_item(
            Key={"pk": key},
            UpdateExpression="SET notify_attempts = if_not_exists(notify_attempts, :zero) + :one",
            ExpressionAttributeValues={":zero": 0, ":one": 1},
            ReturnValues="UPDATED_NEW",
        )
        return int(response["Attributes"]["notify_attempts"])

    def mark_failed(self, key: str) -> None:
        self.table.update_item(
            Key={"pk": key},
            UpdateExpression="SET notify_state = :state",
            ExpressionAttributeValues={":state": "failed"},
        )
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
source .venv/bin/activate && pytest tests/test_store.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/bdfl/store.py tests/test_store.py tests/conftest.py && git commit -m "feat: DynamoDB transaction store with outbox state

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Settings and webhook secret

**Files:**
- Create: `src/bdfl/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py`:

```python
import boto3
import pytest
from moto import mock_aws

from bdfl.config import Settings, get_webhook_url

BASE_ENV = {"TABLE_NAME": "tbl"}


def test_settings_defaults():
    settings = Settings.from_env(BASE_ENV)
    assert settings.league_id == "65522"
    assert settings.table_name == "tbl"
    assert settings.webhook_param_name == "/bdfl/discord/webhook-url"
    assert settings.notify_max_age_seconds == 43200
    assert settings.mfl_user_agent.startswith("bdfl-notifier/")
    assert settings.log_level == "INFO"
    assert settings.webhook_url_override is None


def test_settings_overrides():
    settings = Settings.from_env({
        **BASE_ENV,
        "LEAGUE_ID": "12345",
        "WEBHOOK_PARAM_NAME": "/x/y",
        "NOTIFY_MAX_AGE_SECONDS": "60",
        "MFL_USER_AGENT": "custom/1",
        "LOG_LEVEL": "DEBUG",
        "DISCORD_WEBHOOK_URL": "https://hook",
    })
    assert settings.league_id == "12345"
    assert settings.webhook_param_name == "/x/y"
    assert settings.notify_max_age_seconds == 60
    assert settings.mfl_user_agent == "custom/1"
    assert settings.log_level == "DEBUG"
    assert settings.webhook_url_override == "https://hook"


def test_settings_requires_table_name():
    with pytest.raises(KeyError):
        Settings.from_env({})


def test_get_webhook_url_prefers_override():
    settings = Settings.from_env({**BASE_ENV, "DISCORD_WEBHOOK_URL": "https://hook"})
    assert get_webhook_url(settings) == "https://hook"


@mock_aws
def test_get_webhook_url_reads_secure_string_from_ssm():
    ssm = boto3.client("ssm", region_name="us-east-1")
    ssm.put_parameter(Name="/bdfl/discord/webhook-url", Value="https://secret", Type="SecureString")
    settings = Settings.from_env(BASE_ENV)
    assert get_webhook_url(settings, ssm_client=ssm) == "https://secret"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'bdfl.config'`.

- [ ] **Step 3: Write `src/bdfl/config.py`**

```python
"""Runtime settings from environment variables and SSM."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

import boto3

DEFAULT_USER_AGENT = "bdfl-notifier/1.0 (+https://github.com/btcookies/bdfl-trade-notifier)"


@dataclass(frozen=True)
class Settings:
    league_id: str
    table_name: str
    webhook_param_name: str
    notify_max_age_seconds: int
    mfl_user_agent: str
    log_level: str
    webhook_url_override: str | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        return cls(
            league_id=env.get("LEAGUE_ID", "65522"),
            table_name=env["TABLE_NAME"],
            webhook_param_name=env.get("WEBHOOK_PARAM_NAME", "/bdfl/discord/webhook-url"),
            notify_max_age_seconds=int(env.get("NOTIFY_MAX_AGE_SECONDS", "43200")),
            mfl_user_agent=env.get("MFL_USER_AGENT", DEFAULT_USER_AGENT),
            log_level=env.get("LOG_LEVEL", "INFO"),
            webhook_url_override=env.get("DISCORD_WEBHOOK_URL") or None,
        )


def get_webhook_url(settings: Settings, ssm_client=None) -> str:
    if settings.webhook_url_override:
        return settings.webhook_url_override
    client = ssm_client or boto3.client("ssm")
    response = client.get_parameter(Name=settings.webhook_param_name, WithDecryption=True)
    return response["Parameter"]["Value"]
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
source .venv/bin/activate && pytest tests/test_config.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/bdfl/config.py tests/test_config.py && git commit -m "feat: settings from env and webhook URL from SSM

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Poller orchestration

**Files:**
- Create: `src/bdfl/poller.py`
- Test: `tests/test_poller.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_poller.py`:

```python
import pytest

from bdfl.config import Settings
from bdfl.discord import DiscordError
from bdfl.mfl import MflThrottled
from bdfl.models import LeagueInfo, Player
from bdfl.poller import BACKOFF_SECONDS, LEAGUE_TTL_SECONDS, MAX_ATTEMPTS, NotifyFailed, Poller
from bdfl.store import TransactionStore

NOW = 1788400200
LEAGUE = LeagueInfo(2026, "BDFL", {"0011": "A.J. Mudbone", "0005": "Jeff Janis Fan Club", "0003": "Youth"})
PLAYERS = {
    "13299": Player("13299", "Kittle, George", "SFO", "TE"),
    "15255": Player("15255", "Gainwell, Kenneth", "TBB", "RB"),
    "15733": Player("15733", "Doe, John", "NYG", "WR"),
}
TRADE = {
    "type": "TRADE", "timestamp": str(NOW - 120), "franchise": "0011", "franchise2": "0005",
    "franchise1_gave_up": "15255,", "franchise2_gave_up": "13299,BB_20,", "comments": "",
}
CLAIM_A = {"type": "BBID_WAIVER", "timestamp": str(NOW - 60), "franchise": "0003", "transaction": "15733,|3.00|"}
CLAIM_B = {"type": "BBID_WAIVER", "timestamp": str(NOW - 60), "franchise": "0011", "transaction": "13299,|7.00|"}


def payload(*transactions):
    return {"transactions": {"transaction": list(transactions)}}


class FakeMfl:
    def __init__(self, leagues, payload=None, players=None):
        self.leagues = leagues
        self.payload = payload or {"transactions": {}}
        self.players_map = players or PLAYERS
        self.detect_calls = 0
        self.transactions_calls = 0
        self.players_calls = []
        self.transactions_error = None

    def detect_league(self, now):
        league = self.leagues[min(self.detect_calls, len(self.leagues) - 1)]
        self.detect_calls += 1
        return league

    def transactions(self, year, days=1, types="TRADE,BBID_WAIVER"):
        self.transactions_calls += 1
        if self.transactions_error:
            raise self.transactions_error
        return self.payload

    def players(self, year, ids):
        self.players_calls.append(sorted(ids))
        return {i: self.players_map[i] for i in ids if i in self.players_map}


class FakeWebhook:
    def __init__(self):
        self.posts = []
        self.fail_times = 0

    def post(self, embeds):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise DiscordError("down")
        self.posts.append(embeds)


class FakeClock:
    def __init__(self, now=NOW):
        self.now = float(now)

    def __call__(self):
        return self.now


@pytest.fixture
def harness(dynamodb_table):
    resource, table_name = dynamodb_table
    settings = Settings.from_env({"TABLE_NAME": table_name})
    store = TransactionStore(table_name, resource=resource)
    webhook = FakeWebhook()
    clock = FakeClock()

    def build(mfl):
        return Poller(settings, mfl, store, webhook_factory=lambda: webhook, clock=clock)

    return build, store, webhook, clock


def test_new_trade_is_stored_posted_and_marked_sent(harness):
    build, store, webhook, _ = harness
    mfl = FakeMfl([LEAGUE], payload(TRADE))
    result = build(mfl).run()
    assert (result.league_year, result.fetched, result.new, result.skipped, result.sent, result.failed) == (2026, 1, 1, 0, 1, 0)
    assert result.backoff is False
    assert len(webhook.posts) == 1
    assert webhook.posts[0][0]["title"] == "🚨 Trade Completed"
    row = store.get_many([f"TRADE#{NOW - 120}#0011#0005"])[f"TRADE#{NOW - 120}#0011#0005"]
    assert row["notify_state"] == "sent"
    assert int(row["year"]) == 2026
    assert int(row["notified_at"]) == NOW
    assert row["summary"].startswith("A.J. Mudbone gives up: Kenneth Gainwell, TBB RB")
    assert row["details"]["sides"][1]["assets"] == ["George Kittle, SFO TE", "$20 blind bid dollars"]
    assert mfl.players_calls == [["13299", "15255"]]


def test_old_transaction_is_stored_silently(harness):
    build, store, webhook, _ = harness
    old = {**TRADE, "timestamp": str(NOW - 50000)}
    result = build(FakeMfl([LEAGUE], payload(old))).run()
    assert (result.new, result.skipped, result.sent) == (1, 1, 0)
    assert webhook.posts == []
    assert store.get_many([f"TRADE#{NOW - 50000}#0011#0005"])[f"TRADE#{NOW - 50000}#0011#0005"]["notify_state"] == "skipped"


def test_repeat_polls_do_not_repost_or_refetch_players(harness):
    build, _, webhook, _ = harness
    mfl = FakeMfl([LEAGUE], payload(TRADE))
    poller = build(mfl)
    poller.run()
    second = poller.run()
    third = poller.run()
    assert len(webhook.posts) == 1
    assert (second.fetched, second.new, second.sent) == (1, 0, 0)
    assert third.new == 0
    assert mfl.players_calls == [["13299", "15255"]]


def test_discord_failure_leaves_pending_and_next_poll_sends(harness):
    build, store, webhook, _ = harness
    webhook.fail_times = 1
    poller = build(FakeMfl([LEAGUE], payload(TRADE)))
    first = poller.run()
    key = f"TRADE#{NOW - 120}#0011#0005"
    row = store.get_many([key])[key]
    assert (first.sent, first.failed, row["notify_state"], int(row["notify_attempts"])) == (0, 0, "pending", 1)
    second = poller.run()
    assert second.sent == 1
    assert store.get_many([key])[key]["notify_state"] == "sent"
    assert len(webhook.posts) == 1


def test_fifth_failure_marks_failed_and_raises(harness):
    build, store, webhook, _ = harness
    webhook.fail_times = MAX_ATTEMPTS
    poller = build(FakeMfl([LEAGUE], payload(TRADE)))
    for _ in range(MAX_ATTEMPTS - 1):
        poller.run()
    with pytest.raises(NotifyFailed):
        poller.run()
    key = f"TRADE#{NOW - 120}#0011#0005"
    assert store.get_many([key])[key]["notify_state"] == "failed"
    poller.run()
    assert webhook.posts == []


def test_throttle_sets_backoff_then_resumes(harness):
    build, _, _, clock = harness
    mfl = FakeMfl([LEAGUE], payload(TRADE))
    mfl.transactions_error = MflThrottled("429")
    poller = build(mfl)
    with pytest.raises(MflThrottled):
        poller.run()
    mfl.transactions_error = None
    clock.now = NOW + BACKOFF_SECONDS - 1
    assert poller.run().backoff is True
    assert mfl.transactions_calls == 1
    clock.now = NOW + BACKOFF_SECONDS + 1
    result = poller.run()
    assert result.backoff is False
    assert result.sent == 1


def test_league_info_is_cached_for_six_hours(harness):
    build, _, _, clock = harness
    mfl = FakeMfl([LEAGUE])
    poller = build(mfl)
    poller.run()
    clock.now = NOW + LEAGUE_TTL_SECONDS - 10
    poller.run()
    assert mfl.detect_calls == 1
    clock.now = NOW + LEAGUE_TTL_SECONDS + 10
    poller.run()
    assert mfl.detect_calls == 2


def test_unknown_franchise_triggers_one_refresh(harness):
    build, _, webhook, _ = harness
    renamed = LeagueInfo(2026, "BDFL", {**LEAGUE.franchises, "0099": "New Team"})
    claim = {**CLAIM_A, "franchise": "0099"}
    mfl = FakeMfl([LEAGUE, renamed], payload(claim))
    result = build(mfl).run()
    assert mfl.detect_calls == 2
    assert result.sent == 1
    assert "**New Team**" in webhook.posts[0][0]["description"]


def test_waiver_claims_share_one_message_and_trade_gets_its_own(harness):
    build, store, webhook, _ = harness
    result = build(FakeMfl([LEAGUE], payload(TRADE, CLAIM_A, CLAIM_B))).run()
    assert (result.fetched, result.new, result.sent) == (3, 3, 3)
    assert len(webhook.posts) == 2
    titles = [embeds[0]["title"] for embeds in webhook.posts]
    assert titles == ["🚨 Trade Completed", "✅ Waiver Claims Processed"]
    description = webhook.posts[1][0]["description"]
    assert description.index("A.J. Mudbone") < description.index("Youth")
    keys = [f"WAIVER#{NOW - 60}#0003#15733", f"WAIVER#{NOW - 60}#0011#13299"]
    assert {row["notify_state"] for row in store.get_many(keys).values()} == {"sent"}


def test_empty_poll_makes_no_writes_or_posts(harness):
    build, _, webhook, _ = harness
    mfl = FakeMfl([LEAGUE], {"transactions": {}})
    result = build(mfl).run()
    assert (result.fetched, result.new, result.sent) == (0, 0, 0)
    assert webhook.posts == []
    assert mfl.players_calls == []
    assert result.duration_ms >= 0
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_poller.py -v
```

Expected: `ModuleNotFoundError: No module named 'bdfl.poller'`.

- [ ] **Step 3: Write `src/bdfl/poller.py`**

```python
"""Per-invocation flow: fetch, dedupe, store, notify."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from bdfl.config import Settings
from bdfl.discord import DiscordError, DiscordWebhook
from bdfl.messages import (
    trade_details,
    trade_embed,
    trade_summary,
    waiver_details,
    waiver_messages,
    waiver_summary,
)
from bdfl.mfl import MflClient, MflThrottled
from bdfl.models import (
    LeagueInfo,
    Player,
    Record,
    Trade,
    WaiverClaim,
    parse_transactions,
    referenced_player_ids,
)
from bdfl.store import TransactionStore

BACKOFF_SECONDS = 300
LEAGUE_TTL_SECONDS = 6 * 3600
MAX_ATTEMPTS = 5
SEEN_CACHE_MAX = 2000
FINAL_STATES = {"sent", "skipped", "failed"}

log = logging.getLogger(__name__)


class NotifyFailed(Exception):
    pass


@dataclass
class PollResult:
    league_year: int | None = None
    fetched: int = 0
    new: int = 0
    skipped: int = 0
    sent: int = 0
    failed: int = 0
    backoff: bool = False
    duration_ms: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def build_details(record: Record, league: LeagueInfo, players: dict[str, Player]) -> dict:
    if isinstance(record, Trade):
        return trade_details(record, league, players)
    return waiver_details(record, league, players)


def build_summary(record: Record, details: dict) -> str:
    if isinstance(record, Trade):
        return trade_summary(details)
    return waiver_summary(details)


def make_item(record: Record, league: LeagueInfo, details: dict, state: str, now: float) -> dict:
    return {
        "pk": record.key,
        "type": record.type,
        "year": league.year,
        "timestamp": record.timestamp,
        "franchise_ids": record.franchise_ids,
        "raw": record.raw,
        "details": details,
        "summary": build_summary(record, details),
        "notify_state": state,
        "notify_attempts": 0,
        "first_seen_at": int(now),
    }


class Poller:
    def __init__(
        self,
        settings: Settings,
        mfl: MflClient,
        store: TransactionStore,
        webhook_factory: Callable[[], DiscordWebhook],
        clock: Callable[[], float] = time.time,
    ):
        self.settings = settings
        self.mfl = mfl
        self.store = store
        self.webhook_factory = webhook_factory
        self.clock = clock
        self._league: LeagueInfo | None = None
        self._league_at = 0.0
        self._backoff_until = 0.0
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._webhook: DiscordWebhook | None = None

    def run(self) -> PollResult:
        started = self.clock()
        result = PollResult()
        try:
            if started < self._backoff_until:
                result.backoff = True
                return result
            self._poll(started, result)
            return result
        except MflThrottled:
            self._backoff_until = self.clock() + BACKOFF_SECONDS
            log.warning("MFL throttled; backing off for %s seconds", BACKOFF_SECONDS)
            raise
        finally:
            result.duration_ms = int((self.clock() - started) * 1000)

    # --- steps --------------------------------------------------------------

    def _poll(self, now: float, result: PollResult) -> None:
        league = self._league_info(now)
        result.league_year = league.year
        records = parse_transactions(self.mfl.transactions(league.year))
        result.fetched = len(records)
        candidates = [r for r in records if r.key not in self._seen]
        existing = self.store.get_many([r.key for r in candidates]) if candidates else {}
        new_records = [r for r in candidates if r.key not in existing]
        league = self._ensure_franchises(league, new_records, now)
        to_notify = self._store_new(new_records, league, now, result)
        to_notify += self._pending_existing(candidates, existing)
        self._notify(to_notify, league, now, result)

    def _league_info(self, now: float) -> LeagueInfo:
        if self._league is None or now - self._league_at > LEAGUE_TTL_SECONDS:
            self._league = self.mfl.detect_league(datetime.fromtimestamp(now, tz=UTC))
            self._league_at = now
            log.info("league year %s with %s franchises", self._league.year, len(self._league.franchises))
        return self._league

    def _ensure_franchises(self, league: LeagueInfo, records: list[Record], now: float) -> LeagueInfo:
        """Refresh league info once when a record references an unknown franchise."""
        ids = {fid for r in records for fid in r.franchise_ids}
        if ids - set(league.franchises):
            self._league = None
            return self._league_info(now)
        return league

    def _store_new(
        self, new_records: list[Record], league: LeagueInfo, now: float, result: PollResult
    ) -> list[tuple[Record, dict]]:
        if not new_records:
            return []
        players = self.mfl.players(league.year, referenced_player_ids(new_records))
        to_notify: list[tuple[Record, dict]] = []
        for record in new_records:
            details = build_details(record, league, players)
            too_old = now - record.timestamp > self.settings.notify_max_age_seconds
            state = "skipped" if too_old else "pending"
            if not self.store.put_new(make_item(record, league, details, state, now)):
                log.warning("%s was stored concurrently; leaving it for the next poll", record.key)
                continue
            result.new += 1
            if too_old:
                result.skipped += 1
                self._remember(record.key)
            else:
                to_notify.append((record, details))
        return to_notify

    def _pending_existing(
        self, candidates: list[Record], existing: dict[str, dict]
    ) -> list[tuple[Record, dict]]:
        to_notify: list[tuple[Record, dict]] = []
        for record in candidates:
            row = existing.get(record.key)
            if row is None:
                continue
            attempts = int(row.get("notify_attempts", 0))
            if row.get("notify_state") == "pending" and attempts < MAX_ATTEMPTS:
                to_notify.append((record, row["details"]))
            else:
                self._remember(record.key)
        return to_notify

    def _notify(
        self, to_notify: list[tuple[Record, dict]], league: LeagueInfo, now: float, result: PollResult
    ) -> None:
        if not to_notify:
            return
        trades = [(r, d) for r, d in to_notify if isinstance(r, Trade)]
        claims = [(r, d) for r, d in to_notify if isinstance(r, WaiverClaim)]
        batches: list[tuple[list[dict], list[Record]]] = [
            ([trade_embed(r, d, league)], [r]) for r, d in trades
        ]
        batches += waiver_messages(claims, league)
        exhausted = False
        for embeds, records in batches:
            if not self._deliver(embeds, records, now, result):
                exhausted = True
        if exhausted:
            raise NotifyFailed("some notifications exhausted their attempts; see logs")

    def _deliver(
        self, embeds: list[dict], records: list[Record], now: float, result: PollResult
    ) -> bool:
        """Post one message. Returns False when a record has exhausted its attempts."""
        try:
            self._webhook_client().post(embeds)
        except DiscordError as exc:
            log.error("Discord post failed for %s: %s", [r.key for r in records], exc)
            healthy = True
            for record in records:
                attempts = self.store.bump_attempt(record.key)
                if attempts >= MAX_ATTEMPTS:
                    self.store.mark_failed(record.key)
                    self._remember(record.key)
                    result.failed += 1
                    healthy = False
            return healthy
        for record in records:
            self.store.mark_sent(record.key, int(now))
            self._remember(record.key)
            result.sent += 1
        return True

    # --- helpers ------------------------------------------------------------

    def _webhook_client(self) -> DiscordWebhook:
        if self._webhook is None:
            self._webhook = self.webhook_factory()
        return self._webhook

    def _remember(self, key: str) -> None:
        self._seen[key] = None
        self._seen.move_to_end(key)
        while len(self._seen) > SEEN_CACHE_MAX:
            self._seen.popitem(last=False)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
source .venv/bin/activate && pytest tests/test_poller.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Run the whole suite and the linter**

```bash
source .venv/bin/activate && pytest && ruff check src tests
```

Expected: all tests pass and `All checks passed!`. Fix any import-order findings with `ruff check --fix src tests`.

- [ ] **Step 6: Commit**

```bash
git add src/bdfl/poller.py tests/test_poller.py && git commit -m "feat: poller with outbox retries, backoff, and warm caches

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Lambda handler and live dry run

**Files:**
- Create: `src/handler.py`, `scripts/dry_run.py`
- Test: `tests/test_handler.py`

- [ ] **Step 1: Write the failing handler test**

`tests/test_handler.py`:

```python
import handler
from bdfl.poller import PollResult


class FakePoller:
    def __init__(self):
        self.runs = 0

    def run(self):
        self.runs += 1
        return PollResult(league_year=2026, fetched=2, new=1, sent=1, duration_ms=12)


def test_handler_builds_poller_once_and_returns_result(monkeypatch):
    fake = FakePoller()
    built = []

    def build(settings):
        built.append(settings)
        return fake

    monkeypatch.setenv("TABLE_NAME", "tbl")
    monkeypatch.setattr(handler, "build_poller", build)
    handler._poller = None

    first = handler.handler({}, None)
    second = handler.handler({}, None)

    assert first == {
        "league_year": 2026, "fetched": 2, "new": 1, "skipped": 0,
        "sent": 1, "failed": 0, "backoff": False, "duration_ms": 12,
    }
    assert second == first
    assert fake.runs == 2
    assert len(built) == 1
    assert built[0].table_name == "tbl"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
source .venv/bin/activate && pytest tests/test_handler.py -v
```

Expected: `ModuleNotFoundError: No module named 'handler'`.

- [ ] **Step 3: Write `src/handler.py`**

```python
"""Lambda entry point: one poll per invocation, one poller per container."""

from __future__ import annotations

import json
import logging

from bdfl.config import Settings, get_webhook_url
from bdfl.discord import DiscordWebhook
from bdfl.mfl import MflClient
from bdfl.poller import Poller
from bdfl.store import TransactionStore

log = logging.getLogger("bdfl")
_poller: Poller | None = None


def build_poller(settings: Settings) -> Poller:
    logging.getLogger().setLevel(settings.log_level)
    mfl = MflClient(settings.league_id, settings.mfl_user_agent)
    store = TransactionStore(settings.table_name)
    return Poller(
        settings,
        mfl,
        store,
        webhook_factory=lambda: DiscordWebhook(get_webhook_url(settings)),
    )


def handler(event, context):
    global _poller
    if _poller is None:
        _poller = build_poller(Settings.from_env())
    result = _poller.run().as_dict()
    log.info(json.dumps({"event": "poll", **result}))
    return result
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
source .venv/bin/activate && pytest tests/test_handler.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Write `scripts/dry_run.py`**

```python
#!/usr/bin/env python3
"""Fetch recent MFL transactions and print the Discord messages the bot would post.

Usage:
  python scripts/dry_run.py [--league 65522] [--days 7]
  DISCORD_WEBHOOK_URL=... python scripts/dry_run.py --send   # actually posts them
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from bdfl.config import DEFAULT_USER_AGENT  # noqa: E402
from bdfl.discord import DiscordWebhook  # noqa: E402
from bdfl.messages import trade_embed, waiver_messages  # noqa: E402
from bdfl.mfl import MflClient  # noqa: E402
from bdfl.models import Trade, parse_transactions, referenced_player_ids  # noqa: E402
from bdfl.poller import build_details  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", default=os.environ.get("LEAGUE_ID", "65522"))
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--send", action="store_true", help="post to DISCORD_WEBHOOK_URL")
    args = parser.parse_args()

    mfl = MflClient(args.league, os.environ.get("MFL_USER_AGENT", DEFAULT_USER_AGENT))
    league = mfl.detect_league(datetime.now(tz=UTC))
    print(f"league: {league.name} | year: {league.year} | franchises: {len(league.franchises)}",
          file=sys.stderr)

    records = sorted(parse_transactions(mfl.transactions(league.year, days=args.days)),
                     key=lambda r: r.timestamp)
    players = mfl.players(league.year, referenced_player_ids(records))

    messages: list[list[dict]] = []
    claims = []
    for record in records:
        details = build_details(record, league, players)
        if isinstance(record, Trade):
            messages.append([trade_embed(record, details, league)])
        else:
            claims.append((record, details))
    messages += [embeds for embeds, _ in waiver_messages(claims, league)]

    print(json.dumps(messages, indent=2, ensure_ascii=False))
    print(f"{len(records)} transactions in the last {args.days} days -> {len(messages)} messages",
          file=sys.stderr)

    if args.send:
        url = os.environ.get("DISCORD_WEBHOOK_URL")
        if not url:
            sys.exit("--send requires DISCORD_WEBHOOK_URL in the environment")
        webhook = DiscordWebhook(url)
        for embeds in messages:
            webhook.post(embeds)
        print(f"sent {len(messages)} messages", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run the dry run against the real league**

```bash
source .venv/bin/activate && python scripts/dry_run.py --days 7 > /tmp/bdfl-dry-run.json && python -c "import json; m=json.load(open('/tmp/bdfl-dry-run.json')); print(len(m), 'messages'); print(json.dumps(m[0], indent=1, ensure_ascii=False)[:1200])"
```

Expected: stderr shows `league: Barbara Dodson's Fantasy League | year: 2026 | franchises: 12`, a handful of messages, and the first message has real franchise and player names with no `Unknown player` entries. If a player renders as unknown, note the id and check whether MFL's `PLAYERS=` response omits it before changing any code.

- [ ] **Step 7: Lint and commit**

```bash
source .venv/bin/activate && ruff check src tests scripts && git add src/handler.py scripts/dry_run.py tests/test_handler.py && git commit -m "feat: Lambda handler and live dry-run script

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: SAM template and build

**Files:**
- Create: `template.yaml`, `samconfig.toml`

- [ ] **Step 1: Write `template.yaml`**

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: Posts MFL trades and waiver claims to a Discord channel.

Parameters:
  LeagueId:
    Type: String
    Default: '65522'
  WebhookParameterName:
    Type: String
    Default: /bdfl/discord/webhook-url
    Description: SSM SecureString parameter that holds the Discord webhook URL.
  AlertEmail:
    Type: String
    Default: ''
    Description: Optional. Email to notify when the poll function keeps failing.
  PollSchedule:
    Type: String
    Default: rate(1 minute)
  NotifyMaxAgeSeconds:
    Type: Number
    Default: 43200
    Description: Transactions older than this are stored without posting.
  MflUserAgent:
    Type: String
    Default: bdfl-notifier/1.0 (+https://github.com/btcookies/bdfl-trade-notifier)

Conditions:
  HasAlertEmail: !Not [!Equals [!Ref AlertEmail, '']]

Resources:
  TransactionsTable:
    Type: AWS::DynamoDB::Table
    DeletionPolicy: Retain
    UpdateReplacePolicy: Retain
    Properties:
      TableName: !Sub '${AWS::StackName}-transactions'
      BillingMode: PROVISIONED
      ProvisionedThroughput:
        ReadCapacityUnits: 5
        WriteCapacityUnits: 5
      AttributeDefinitions:
        - AttributeName: pk
          AttributeType: S
      KeySchema:
        - AttributeName: pk
          KeyType: HASH

  PollFunction:
    Type: AWS::Serverless::Function
    Properties:
      FunctionName: !Sub '${AWS::StackName}-poll'
      CodeUri: src/
      Handler: handler.handler
      Runtime: python3.13
      Architectures: [arm64]
      MemorySize: 256
      Timeout: 30
      ReservedConcurrentExecutions: 1
      Environment:
        Variables:
          LEAGUE_ID: !Ref LeagueId
          TABLE_NAME: !Ref TransactionsTable
          WEBHOOK_PARAM_NAME: !Ref WebhookParameterName
          NOTIFY_MAX_AGE_SECONDS: !Ref NotifyMaxAgeSeconds
          MFL_USER_AGENT: !Ref MflUserAgent
          LOG_LEVEL: INFO
      Policies:
        - DynamoDBCrudPolicy:
            TableName: !Ref TransactionsTable
        - Statement:
            - Effect: Allow
              Action: ssm:GetParameter
              Resource: !Sub 'arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter${WebhookParameterName}'
      Events:
        Poll:
          Type: ScheduleV2
          Properties:
            Name: !Sub '${AWS::StackName}-poll'
            Description: Poll MFL for new trades and waiver claims.
            ScheduleExpression: !Ref PollSchedule
            FlexibleTimeWindow:
              Mode: 'OFF'
            RetryPolicy:
              MaximumRetryAttempts: 0

  PollLogGroup:
    Type: AWS::Logs::LogGroup
    Properties:
      LogGroupName: !Sub '/aws/lambda/${PollFunction}'
      RetentionInDays: 14

  AlertTopic:
    Type: AWS::SNS::Topic
    Condition: HasAlertEmail
    Properties:
      Subscription:
        - Endpoint: !Ref AlertEmail
          Protocol: email

  PollErrorsAlarm:
    Type: AWS::CloudWatch::Alarm
    Condition: HasAlertEmail
    Properties:
      AlarmDescription: The bdfl-notifier poll function is failing repeatedly.
      Namespace: AWS/Lambda
      MetricName: Errors
      Dimensions:
        - Name: FunctionName
          Value: !Ref PollFunction
      Statistic: Sum
      Period: 900
      EvaluationPeriods: 1
      Threshold: 3
      ComparisonOperator: GreaterThanOrEqualToThreshold
      TreatMissingData: notBreaching
      AlarmActions: [!Ref AlertTopic]
      OKActions: [!Ref AlertTopic]

Outputs:
  TableName:
    Value: !Ref TransactionsTable
  FunctionName:
    Value: !Ref PollFunction
```

- [ ] **Step 2: Write `samconfig.toml`**

```toml
version = 0.1

[default.global.parameters]
stack_name = "bdfl-notifier"
region = "us-east-1"

[default.build.parameters]
cached = true
parallel = true

[default.deploy.parameters]
capabilities = "CAPABILITY_IAM"
resolve_s3 = true
confirm_changeset = false
fail_on_empty_changeset = false
```

- [ ] **Step 3: Validate and build**

```bash
sam validate --lint && sam build
```

Expected: `template.yaml is a valid SAM Template` followed by `Build Succeeded`. `sam validate --lint` does not need AWS credentials. If `sam validate` without `--lint` complains about missing credentials, run only the `--lint` form.

- [ ] **Step 4: Check the built artifact contains the package and its dependency**

```bash
ls .aws-sam/build/PollFunction/ && ls .aws-sam/build/PollFunction/bdfl/ && python3 -c "import sys; sys.path.insert(0, '.aws-sam/build/PollFunction'); import handler; print('import ok')"
```

Expected: `handler.py`, `bdfl/`, `requests/` and its dependencies in the first listing; the eight `bdfl` modules in the second; `import ok`.

- [ ] **Step 5: Commit**

```bash
git add template.yaml samconfig.toml && git commit -m "infra: SAM template with 1-minute schedule, table, alarm

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 12: GitHub Actions CI, deploy workflow, and one-time OIDC role

**Files:**
- Create: `.github/workflows/ci.yml`, `.github/workflows/deploy.yml`, `infra/github-oidc.yaml`

- [ ] **Step 1: Write `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main, discord-port]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      - run: pip install -r requirements-dev.txt
      - run: ruff check src tests scripts
      - run: pytest
      - uses: aws-actions/setup-sam@v2
      - run: sam validate --lint
```

- [ ] **Step 2: Write `.github/workflows/deploy.yml`**

```yaml
name: Deploy

on:
  push:
    branches: [main]

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    if: vars.AWS_DEPLOY_ROLE_ARN != ''
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      - uses: aws-actions/setup-sam@v2
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.AWS_DEPLOY_ROLE_ARN }}
          aws-region: us-east-1
      - run: sam build
      - run: sam deploy --no-confirm-changeset --no-fail-on-empty-changeset
```

- [ ] **Step 3: Write `infra/github-oidc.yaml`**

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: One-time GitHub Actions OIDC deploy role for bdfl-trade-notifier.

Parameters:
  GitHubRepo:
    Type: String
    Default: btcookies/bdfl-trade-notifier
  Branch:
    Type: String
    Default: main
  StackNamePrefix:
    Type: String
    Default: bdfl-notifier
    Description: Must match stack_name in samconfig.toml.

Resources:
  GitHubOidcProvider:
    Type: AWS::IAM::OIDCProvider
    Properties:
      Url: https://token.actions.githubusercontent.com
      ClientIdList:
        - sts.amazonaws.com
      ThumbprintList:
        - 6938fd4d98bab03faadb97b34396831e3780aea1

  DeployRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: !Sub '${StackNamePrefix}-github-deploy'
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Federated: !Ref GitHubOidcProvider
            Action: sts:AssumeRoleWithWebIdentity
            Condition:
              StringEquals:
                token.actions.githubusercontent.com:aud: sts.amazonaws.com
                token.actions.githubusercontent.com:sub: !Sub 'repo:${GitHubRepo}:ref:refs/heads/${Branch}'
      Policies:
        - PolicyName: sam-deploy
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Sid: CloudFormation
                Effect: Allow
                Action: cloudformation:*
                Resource:
                  - !Sub 'arn:aws:cloudformation:${AWS::Region}:${AWS::AccountId}:stack/${StackNamePrefix}*/*'
                  - !Sub 'arn:aws:cloudformation:${AWS::Region}:${AWS::AccountId}:stack/aws-sam-cli-managed-default/*'
                  - !Sub 'arn:aws:cloudformation:${AWS::Region}:aws:transform/Serverless-2016-10-31'
              - Sid: SamArtifactBucket
                Effect: Allow
                Action:
                  - s3:CreateBucket
                  - s3:GetBucketLocation
                  - s3:ListBucket
                  - s3:GetObject
                  - s3:PutObject
                  - s3:GetBucketPolicy
                  - s3:PutBucketPolicy
                  - s3:GetBucketVersioning
                  - s3:PutBucketVersioning
                  - s3:GetEncryptionConfiguration
                  - s3:PutEncryptionConfiguration
                  - s3:GetBucketPublicAccessBlock
                  - s3:PutBucketPublicAccessBlock
                  - s3:GetBucketTagging
                  - s3:PutBucketTagging
                  - s3:GetLifecycleConfiguration
                  - s3:PutLifecycleConfiguration
                Resource:
                  - arn:aws:s3:::aws-sam-cli-managed-default*
                  - arn:aws:s3:::aws-sam-cli-managed-default*/*
              - Sid: Lambda
                Effect: Allow
                Action: lambda:*
                Resource: !Sub 'arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:${StackNamePrefix}*'
              - Sid: DynamoDB
                Effect: Allow
                Action: dynamodb:*
                Resource: !Sub 'arn:aws:dynamodb:${AWS::Region}:${AWS::AccountId}:table/${StackNamePrefix}*'
              - Sid: Scheduler
                Effect: Allow
                Action: scheduler:*
                Resource: !Sub 'arn:aws:scheduler:${AWS::Region}:${AWS::AccountId}:schedule/default/${StackNamePrefix}*'
              - Sid: LogGroups
                Effect: Allow
                Action:
                  - logs:CreateLogGroup
                  - logs:DeleteLogGroup
                  - logs:PutRetentionPolicy
                  - logs:DeleteRetentionPolicy
                  - logs:TagResource
                  - logs:UntagResource
                  - logs:ListTagsForResource
                Resource: !Sub 'arn:aws:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/lambda/${StackNamePrefix}*'
              - Sid: LogGroupsDescribe
                Effect: Allow
                Action: logs:DescribeLogGroups
                Resource: '*'
              - Sid: Sns
                Effect: Allow
                Action: sns:*
                Resource: !Sub 'arn:aws:sns:${AWS::Region}:${AWS::AccountId}:${StackNamePrefix}*'
              - Sid: Alarms
                Effect: Allow
                Action:
                  - cloudwatch:PutMetricAlarm
                  - cloudwatch:DeleteAlarms
                  - cloudwatch:DescribeAlarms
                Resource: !Sub 'arn:aws:cloudwatch:${AWS::Region}:${AWS::AccountId}:alarm:${StackNamePrefix}*'
              - Sid: Iam
                Effect: Allow
                Action:
                  - iam:CreateRole
                  - iam:DeleteRole
                  - iam:GetRole
                  - iam:PassRole
                  - iam:AttachRolePolicy
                  - iam:DetachRolePolicy
                  - iam:PutRolePolicy
                  - iam:DeleteRolePolicy
                  - iam:GetRolePolicy
                  - iam:TagRole
                  - iam:UntagRole
                  - iam:UpdateAssumeRolePolicy
                Resource: !Sub 'arn:aws:iam::${AWS::AccountId}:role/${StackNamePrefix}*'

Outputs:
  DeployRoleArn:
    Description: Set this as the GitHub repository variable AWS_DEPLOY_ROLE_ARN.
    Value: !GetAtt DeployRole.Arn
```

- [ ] **Step 4: Lint the OIDC template and the workflows**

```bash
sam validate --lint --template infra/github-oidc.yaml && python3 -c "import yaml,sys; [yaml.safe_load(open(p)) for p in ['.github/workflows/ci.yml', '.github/workflows/deploy.yml']]; print('workflows parse')"
```

Expected: the OIDC template is reported valid (it is plain CloudFormation, which `sam validate --lint` accepts) and `workflows parse`. If `yaml` is not importable, run `source .venv/bin/activate && pip install pyyaml` first.

- [ ] **Step 5: Commit**

```bash
git add .github infra && git commit -m "ci: test on PR, deploy on main via GitHub OIDC

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 13: README, final verification, and hand-off

**Files:**
- Modify: `README.md` (replace entirely)

- [ ] **Step 1: Write `README.md`**

````markdown
# bdfl-trade-notifier

Posts completed trades and processed blind-bid waiver claims from the Barbara Dodson Fantasy League on MyFantasyLeague (MFL) to the league's Discord channel, within about a minute of MFL processing them.

## How it works

One Lambda function runs every minute. Each run:

1. detects the current league year from MFL's league export (no yearly config change needed),
2. fetches the last day of trades and blind-bid waivers in one request,
3. dedupes against a DynamoDB table that also acts as the outbox,
4. looks up only the players referenced by anything new,
5. posts embeds to a Discord webhook and marks each row as sent.

A row that fails to post is retried on the next run, up to five times. MFL rate limiting triggers a five-minute backoff. Everything fits in the AWS always-free tier at one poll per minute.

Design: `docs/superpowers/specs/2026-09-04-discord-notifier-design.md`.

## One-time setup

You need the AWS CLI and SAM CLI (`brew install awscli aws-sam-cli`) and Python 3.13.

1. Configure AWS credentials for the league's account:

   ```bash
   aws configure
   ```

   Use region `us-east-1`, or change `region` in `samconfig.toml`.

2. Create the Discord webhook: open the channel's settings, choose Integrations, then Webhooks, then New Webhook. Name it `BDFL`, copy the webhook URL.

3. Store the URL as an encrypted SSM parameter:

   ```bash
   aws ssm put-parameter --name /bdfl/discord/webhook-url --type SecureString --value 'https://discord.com/api/webhooks/...'
   ```

4. Build and deploy. The first deploy is guided; accept the defaults, and optionally set `AlertEmail` to get an email when polling keeps failing:

   ```bash
   sam build && sam deploy --guided
   ```

   Later deploys are just `sam build && sam deploy`.

5. Confirm it is polling:

   ```bash
   sam logs --stack-name bdfl-notifier --name PollFunction --tail
   ```

   Each run logs one JSON line like `{"event": "poll", "league_year": 2026, "fetched": 12, "new": 0, ...}`.

6. Once Discord posts look right, delete the old Serverless stack from the CloudFormation console (it is named after the old `bdfl-trade-notifier` service). That removes the old functions, queue, and tables and silences the GroupMe bot.

## Preview what would post

```bash
python3.13 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt
python scripts/dry_run.py --days 7
```

Prints the exact Discord payloads for the last 7 days without sending anything. Add `--send` with `DISCORD_WEBHOOK_URL` set in the environment to post them for real, for example to test a new webhook.

## Development

```bash
source .venv/bin/activate
pytest                 # unit tests; no network, no AWS
ruff check src tests scripts
sam validate --lint
```

Layout: `src/handler.py` is the Lambda entry point; `src/bdfl/` holds the MFL client, rendering, Discord client, store, and poller; `tests/` mirrors it.

## Operations

- **Schedule:** the `PollSchedule` parameter, default `rate(1 minute)`.
- **First-deploy replay:** transactions older than `NotifyMaxAgeSeconds` (default 12 hours) are stored without posting.
- **Higher MFL limits:** register a client User-Agent on MFL's API page and set the `MflUserAgent` parameter.
- **Alarm:** with `AlertEmail` set, three or more failed runs in 15 minutes send an email. Confirm the SNS subscription email once.
- **Logs:** 14 day retention in the function's log group.
- **Private league:** MFL supports an `APIKEY` query parameter for exports. If the league is ever made private, add it to `MflClient._get` and store the key in SSM alongside the webhook URL.

## Push-to-deploy (optional)

1. Apply the one-time role: `aws cloudformation deploy --template-file infra/github-oidc.yaml --stack-name bdfl-notifier-github-oidc --capabilities CAPABILITY_NAMED_IAM`
2. Copy the `DeployRoleArn` output into the GitHub repository variable `AWS_DEPLOY_ROLE_ARN`.
3. Pushes to `main` then run `sam build` and `sam deploy` in GitHub Actions. Pull requests run tests and template linting only.

## Future

The transactions table stores the league year and rendered details for every trade and claim, which is the seed for a hall-of-fame feature. MFL's league export lists every season since 2016, so prior years can be backfilled. Slash commands would add a Discord application and an interactions endpoint alongside this poller.
````

- [ ] **Step 2: Run the full verification**

```bash
source .venv/bin/activate && pytest && ruff check src tests scripts && sam validate --lint && sam build && git status --short
```

Expected: all tests pass, `All checks passed!`, the template is valid, `Build Succeeded`, and `git status` shows only `README.md` modified.

- [ ] **Step 3: Commit**

```bash
git add README.md && git commit -m "docs: README for the Discord notifier

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 4: Hand-off**

Report to the owner: the branch name, the test count, the dry-run message count, and the six setup steps from the README. Do not push, merge, or deploy; those are the owner's calls and deploying needs credentials only the owner has.

---

## Spec coverage map

| Spec section | Task |
|---|---|
| 3 verified MFL facts (dict-vs-list, error body, 404, asset codes, pacing) | 2, 3, 6 |
| 4 per-invocation flow, reliability rules, backoff | 9, 11 |
| 5 year detection | 6 |
| 6 data model | 7, 9 (`make_item`) |
| 7 rendering | 3, 4 |
| 8 Discord messages and limits | 4, 5 |
| 9 configuration | 8, 11 |
| 10 infrastructure | 11 |
| 12 error handling and edge cases | 5, 6, 9 |
| 13 testing, dry run | 2 to 10 |
| 14 continuous delivery | 12 |
| 15 layout, deletions, gitignore | 1 |
| 16 migration and hand-off | 13 |
