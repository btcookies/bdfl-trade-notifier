# Hall of Records, Plan 4 of 4: Discord Recap and Season Wrap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Post a recap to the league's Discord channel after every completed week of the season and a season wrap after the final, from the same job that rebuilds the site, never posting the same week twice.

**Architecture:** `hof/discord/notify.py` decides what to post from the `Model` plus a one-line state file; `recap.py` and `wrap.py` turn the Plan 2 facts into one embed each; posting goes through the notifier's existing `bdfl.discord.DiscordWebhook`. `python -m hof notify` runs it, with `--dry-run` to print the embed instead of sending it. The workflow gains a gated notify step and a state-file commit, and picks up the re-run hardening.

**Tech Stack:** Python 3.13, `requests` through `bdfl.discord`, pytest with `responses` for the webhook.

**Spec:** `docs/superpowers/specs/2026-09-06-hall-of-records-design.md`, section 8 and the workflow bullets of section 9.

---

## What the earlier plans give you

- `hof.stats.model.Model` with `league`, `records`, `hall`, `through`, `champions`, and `league.season(year)` returning a `Season`. `Season.final` is the final's `Game` (with `week`, `winner`, `loser`, whose `Lineup`s have `franchise_id` and `score`) or None. `Season.transactions.week_locked_at(week, start_week)` returns the `LOCK_ALL_PLAYERS` timestamp that started that week, or None. `Season.weeks[n].matchups` is a tuple of `(home id, away id)` pairs and `Season.weeks[n].lineups[id].score` is None until MFL has scored the lineup.
- `hof.stats.milestones.recap_facts(league, tables, (year, week)) -> RecapFacts` with `year, week, playoff, high_score (name, score) | None, top_starter (player, franchise, points, vor) | None, new_records, milestones, series_firsts, playoff_picture, bracket` (the last five are tuples of finished sentences). `season_awards(league, tables, year) -> SeasonAwards` with `top_scorer (player, franchise, points)`, `best_vor (player, franchise, vor)`, `best_manager (franchise, efficiency)`, `most_bench_left (franchise, points)`, `champion (name, record, points_for, rank | None)`, each None when unavailable.
- `model.hall.players` are `PlayerPlaque`s with `name, position, class_year, starts, points, vor, titles`; `model.hall.franchises` are `FranchisePlaque`s with `name, class_year, titles`.
- `bdfl.discord.DiscordWebhook(url).post(embeds)` raises `DiscordPermanentError` (never retry) or `DiscordError` (transient) and handles a short 429 itself. `bdfl.messages` has `MAX_DESCRIPTION` (4096), `MAX_FIELD_VALUE` (1024), `MAX_MESSAGE_CHARS` (6000), `escape_markdown(text)`, `truncate(text, limit)`, and `embed_length(embed)`. Do not import `bdfl.config`: it imports boto3, which the workflow does not install.
- `Config.site_base_url` is the site's URL for the footer. Tests build a `Model` with `compute(four_team_league().seasons, rules)`; that league has no lock times, so tests add them with `dataclasses.replace` on the season's `TransactionLog`.

## Decisions

- **Completion rule, as in the spec:** week k of a season is complete when its lock exists, `now` is at least 40 hours after it, and every matchup listed for the week has both lineups scored. The newest complete week is the largest such k in the newest season that has one.
- **Wrap instead of recap** when the newest complete week is the week of the season's final.
- **State** lives in `data/notify-state.json` as `{"season": 2026, "week": 9, "kind": "recap"}`. A run posts only when the newest complete week is later than the state, then rewrites the state. A failed post raises and leaves the state untouched.
- **Nothing to post is success.** The offseason, an in-progress week, and a week already posted all exit 0 with a printed reason, so the workflow step stays green.
- **Preview before sending.** `--dry-run` prints the embed as JSON without touching Discord or the state; `--year` and `--week` force a specific week for previews against past seasons.
- **The webhook URL comes from `DISCORD_WEBHOOK_URL`** in the environment. A small local check rejects anything that is not an `https://discord.com/api/webhooks/...` URL before a request is made; the URL is never logged.
- **Embed budget:** one embed per post. Fields are capped by dropping whole lines from the end and appending "…and N more", so a wild week cannot exceed Discord's limits.

## File structure

| Path | Responsibility |
|---|---|
| `hof/discord/__init__.py` | empty |
| `hof/discord/notify.py` | webhook URL check, state file, completion rule, `decide()` and `run()` |
| `hof/discord/recap.py` | `recap_embed(facts, site_url)` |
| `hof/discord/wrap.py` | `wrap_embed(model, year, awards, site_url)` |
| `hof/__main__.py` | gains `notify [--dry-run] [--year Y --week W]` |
| `.github/workflows/hof.yml` | notify step, state commit, re-run hardening |
| `tests/hof/test_hof_notify.py`, `test_hof_recap.py`, `test_hof_wrap.py` | tests per module |

Conventions as before: repo root, virtualenv active (or the sibling `../wonderful-engelbart-a49f68/.venv/bin/python` when this worktree has none), `pytest`, `ruff check src tests scripts hof`, one commit per task with the `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` trailer.

---

### Task 1: Completion rule, state file, and the decision

**Files:**
- Create: `hof/discord/__init__.py`, `hof/discord/notify.py`
- Test: `tests/hof/test_hof_notify.py`

- [ ] **Step 1: Write the failing tests**

`tests/hof/test_hof_notify.py`:

```python
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from synthetic import four_team_league

from hof.config import HallRules
from hof.discord import notify
from hof.discord.notify import Decision, State
from hof.model.transactions import TransactionLog
from hof.stats.league import League
from hof.stats.model import compute

RULES = HallRules(player_min_vor=30, player_min_starts=3, franchise_min_titles=1)
LOCKS = (1_000, 2_000, 3_000, 4_000)  # 2020 weeks 1 to 4
HOURS = 3600


def league_with_locks(week4_scored: bool = True) -> League:
    """The synthetic league with lock times on 2020 and, optionally, week 4 left unscored."""
    league = four_team_league()
    s2020 = league.season(2020)
    s2020 = replace(s2020, transactions=replace(s2020.transactions, lock_times=LOCKS))
    if not week4_scored:
        week4 = s2020.weeks[4]
        lineups = {fid: replace(lineup, score=None) for fid, lineup in week4.lineups.items()}
        s2020 = replace(s2020, weeks={**s2020.weeks, 4: replace(week4, lineups=lineups)})
    s2021 = league.season(2021)
    s2021 = replace(s2021, transactions=replace(s2021.transactions, lock_times=(10_000,)))
    return League.build([s2020, s2021])


def at(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch, UTC)


def test_week_is_complete_forty_hours_after_its_lock():
    season = league_with_locks().season(2020)
    assert notify.week_complete(season, 3, at(3_000 + 40 * HOURS - 1)) is False
    assert notify.week_complete(season, 3, at(3_000 + 40 * HOURS)) is True
    assert notify.week_complete(season, 5, at(10 ** 9)) is False  # no such lock


def test_week_with_an_unscored_matchup_is_not_complete():
    season = league_with_locks(week4_scored=False).season(2020)
    assert notify.week_complete(season, 4, at(10 ** 9)) is False
    assert notify.week_complete(season, 3, at(10 ** 9)) is True


def test_newest_complete_week_prefers_the_newest_season():
    league = league_with_locks()
    assert notify.newest_complete_week(league, at(10_000 + 40 * HOURS)) == (2021, 1)
    assert notify.newest_complete_week(league, at(4_000 + 40 * HOURS)) == (2020, 4)
    assert notify.newest_complete_week(league, at(500)) is None


def test_state_round_trip(tmp_path):
    path = tmp_path / "notify-state.json"
    assert notify.load_state(path) is None
    notify.save_state(path, State(2020, 4, "wrap"))
    assert json.loads(path.read_text()) == {"season": 2020, "week": 4, "kind": "wrap"}
    assert notify.load_state(path) == State(2020, 4, "wrap")


def test_decide_recap_wrap_and_nothing():
    league = league_with_locks()
    model = compute(league.seasons, RULES)
    # 2020 week 4 is the final: a wrap
    assert notify.decide(model, None, at(4_000 + 40 * HOURS)) == Decision("wrap", 2020, 4)
    # a regular-season week: a recap
    assert notify.decide(model, None, at(3_000 + 40 * HOURS)) == Decision("recap", 2020, 3)
    # already posted
    assert notify.decide(model, State(2020, 3, "recap"), at(3_000 + 40 * HOURS)) is None
    # posted an older week: post the newest complete one only
    assert notify.decide(model, State(2020, 1, "recap"), at(4_000 + 40 * HOURS)) == Decision("wrap", 2020, 4)
    # nothing complete yet
    assert notify.decide(model, None, at(500)) is None


@pytest.mark.parametrize(
    "url, ok",
    [
        ("https://discord.com/api/webhooks/123/abc", True),
        ("https://discordapp.com/api/webhooks/123/abc", True),
        ("http://discord.com/api/webhooks/123/abc", False),
        ("https://example.com/api/webhooks/123/abc", False),
        ("https://discord.com/api/other/123", False),
        ("", False),
    ],
)
def test_webhook_url_check(url, ok):
    if ok:
        assert notify.webhook_url({"DISCORD_WEBHOOK_URL": url}) == url
    else:
        with pytest.raises(notify.NotifyError):
            notify.webhook_url({"DISCORD_WEBHOOK_URL": url})


def test_run_posts_once_and_records_state(tmp_path):
    league = league_with_locks()
    model = compute(league.seasons, RULES)
    posted: list[list[dict]] = []

    class FakeWebhook:
        def post(self, embeds):
            posted.append(embeds)

    path = tmp_path / "notify-state.json"
    now = at(3_000 + 40 * HOURS)
    outcome = notify.run(model, "https://example.test/", path, now, FakeWebhook())
    assert outcome.posted and outcome.decision == Decision("recap", 2020, 3)
    assert len(posted) == 1 and posted[0][0]["title"] == "📜 Week 3 in the record books"
    assert notify.load_state(path) == State(2020, 3, "recap")

    again = notify.run(model, "https://example.test/", path, now, FakeWebhook())
    assert not again.posted and "already posted" in again.reason
    assert len(posted) == 1


def test_run_leaves_state_alone_when_the_post_fails(tmp_path):
    league = league_with_locks()
    model = compute(league.seasons, RULES)

    class FailingWebhook:
        def post(self, embeds):
            raise RuntimeError("boom")

    path = tmp_path / "notify-state.json"
    with pytest.raises(RuntimeError):
        notify.run(model, "https://example.test/", path, at(3_000 + 40 * HOURS), FailingWebhook())
    assert notify.load_state(path) is None


def test_run_dry_run_prints_without_posting_or_saving(tmp_path, capsys):
    league = league_with_locks()
    model = compute(league.seasons, RULES)
    path = tmp_path / "notify-state.json"
    outcome = notify.run(model, "https://example.test/", path, at(4_000 + 40 * HOURS), webhook=None, dry_run=True)
    assert not outcome.posted and outcome.decision == Decision("wrap", 2020, 4)
    out = capsys.readouterr().out
    assert json.loads(out)["title"] == "🏆 2020 season wrap"
    assert notify.load_state(path) is None


def test_run_forced_week_ignores_state(tmp_path, capsys):
    league = league_with_locks()
    model = compute(league.seasons, RULES)
    path = tmp_path / "notify-state.json"
    notify.save_state(path, State(2021, 1, "recap"))
    outcome = notify.run(model, "https://example.test/", path, at(10 ** 9), webhook=None, dry_run=True, force=(2020, 2))
    assert outcome.decision == Decision("recap", 2020, 2)
    assert json.loads(capsys.readouterr().out)["title"] == "📜 Week 2 in the record books"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_notify.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'hof.discord'`.

- [ ] **Step 3: Implement**

`hof/discord/__init__.py`: empty.

`hof/discord/notify.py` (the two embed builders it imports are Tasks 2 and 3; until then the tests that post will fail on the import, which is expected):

```python
"""Decide whether this run posts a weekly recap or a season wrap, and post it once."""

from __future__ import annotations

import json
import logging
import urllib.parse
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from hof.discord.recap import recap_embed
from hof.discord.wrap import wrap_embed
from hof.model.season import Season
from hof.stats import milestones
from hof.stats.league import League
from hof.stats.model import Model

log = logging.getLogger(__name__)

COMPLETE_AFTER_SECONDS = 40 * 3600  # Sunday 17:00 UTC lock + 40 h = Tuesday 09:00 UTC


class NotifyError(ValueError):
    """Bad configuration: the run cannot post."""


class Webhook(Protocol):
    def post(self, embeds: list[dict]) -> None: ...


@dataclass(frozen=True)
class State:
    season: int
    week: int
    kind: str  # recap or wrap

    @property
    def key(self) -> tuple[int, int]:
        return (self.season, self.week)


@dataclass(frozen=True)
class Decision:
    kind: str  # recap or wrap
    year: int
    week: int


@dataclass(frozen=True)
class Outcome:
    posted: bool
    decision: Decision | None
    reason: str


def webhook_url(env: Mapping[str, str]) -> str:
    """The webhook URL from the environment, checked for shape; never log the value."""
    url = (env.get("DISCORD_WEBHOOK_URL") or "").strip()
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    good_host = host in ("discord.com", "discordapp.com") or host.endswith((".discord.com", ".discordapp.com"))
    if parts.scheme != "https" or not good_host or "/api/webhooks/" not in parts.path:
        raise NotifyError("DISCORD_WEBHOOK_URL is missing or does not look like a Discord webhook URL")
    return url


def load_state(path: Path) -> State | None:
    try:
        raw = json.loads(path.read_text())
        return State(int(raw["season"]), int(raw["week"]), str(raw["kind"]))
    except FileNotFoundError:
        return None
    except (ValueError, KeyError, TypeError) as exc:
        log.warning("ignoring unreadable notify state %s: %s", path, exc)
        return None


def save_state(path: Path, state: State) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state)) + "\n")


def week_complete(season: Season, week: int, now: datetime) -> bool:
    """Locked at least 40 hours ago and every listed matchup has both lineups scored."""
    lock = season.transactions.week_locked_at(week, season.start_week)
    if lock is None or now.timestamp() < lock + COMPLETE_AFTER_SECONDS:
        return False
    listed = season.weeks.get(week)
    if listed is None or not listed.matchups:
        return False
    return all(
        listed.lineups.get(fid) is not None and listed.lineups[fid].score is not None
        for pair in listed.matchups
        for fid in pair
    )


def newest_complete_week(league: League, now: datetime) -> tuple[int, int] | None:
    for season in reversed(league.seasons):
        complete = [week for week in sorted(season.weeks) if week_complete(season, week, now)]
        if complete:
            return season.year, complete[-1]
    return None


def decide(model: Model, state: State | None, now: datetime) -> Decision | None:
    newest = newest_complete_week(model.league, now)
    if newest is None:
        return None
    if state is not None and state.key >= newest:
        return None
    year, week = newest
    final = model.league.season(year).final
    kind = "wrap" if final is not None and final.week == week else "recap"
    return Decision(kind, year, week)


def build_embed(model: Model, decision: Decision, site_url: str) -> dict[str, Any]:
    if decision.kind == "wrap":
        awards = milestones.season_awards(model.league, model.records, decision.year)
        return wrap_embed(model, decision.year, awards, site_url)
    facts = milestones.recap_facts(model.league, model.records, (decision.year, decision.week))
    return recap_embed(facts, site_url)


def run(
    model: Model,
    site_url: str,
    state_path: Path,
    now: datetime,
    webhook: Webhook | None,
    dry_run: bool = False,
    force: tuple[int, int] | None = None,
) -> Outcome:
    """Post the newest complete week once. With dry_run, print the embed instead; with force,
    build the given (year, week) regardless of completion or state (previews only)."""
    if force is not None:
        year, week = force
        final = model.league.season(year).final
        decision: Decision | None = Decision("wrap" if final is not None and final.week == week else "recap", year, week)
    else:
        state = load_state(state_path)
        decision = decide(model, state, now)
        if decision is None:
            newest = newest_complete_week(model.league, now)
            reason = "no complete week yet" if newest is None else f"already posted {newest[0]} week {newest[1]}"
            log.info("nothing to post: %s", reason)
            return Outcome(False, None, reason)
    embed = build_embed(model, decision, site_url)
    if dry_run:
        print(json.dumps(embed, ensure_ascii=False, indent=2))
        return Outcome(False, decision, "dry run")
    if webhook is None:
        raise NotifyError("no webhook to post with")
    webhook.post([embed])
    if force is None:
        save_state(state_path, State(decision.year, decision.week, decision.kind))
    log.info("posted %s for %s week %s", decision.kind, decision.year, decision.week)
    return Outcome(True, decision, "posted")


def now_utc() -> datetime:
    return datetime.now(UTC)
```

- [ ] **Step 4: Run the tests that do not need the embeds**

Run: `pytest tests/hof/test_hof_notify.py -v -k "complete or state or decide or webhook_url"`
Expected: those pass; the `run_*` tests still fail on the missing `hof.discord.recap` import until Task 2. If the import error blocks collection of the whole module, create `hof/discord/recap.py` and `hof/discord/wrap.py` now with just the function signatures raising `NotImplementedError`, and replace them in the next two tasks.

- [ ] **Step 5: Lint and commit**

Run: `ruff check hof tests/hof`
Expected: no issues.

```bash
git add hof/discord tests/hof/test_hof_notify.py
git commit -m "feat(hof): notify decision, completion rule, and state file

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: The weekly recap embed

**Files:**
- Create: `hof/discord/recap.py`
- Test: `tests/hof/test_hof_recap.py`

- [ ] **Step 1: Write the failing tests**

`tests/hof/test_hof_recap.py`:

```python
import pytest
from synthetic import four_team_league

from bdfl.messages import MAX_FIELD_VALUE, embed_length
from hof.discord import recap
from hof.stats import careers, milestones, records

SITE = "https://example.test/hof/"


@pytest.fixture(scope="module")
def tables():
    league = four_team_league()
    return league, records.records_book(league, careers.careers(league))


def test_final_week_recap(tables):
    league, book = tables
    facts = milestones.recap_facts(league, book, (2020, 4))
    embed = recap.recap_embed(facts, SITE)
    assert embed["title"] == "📜 Week 4 in the record books"
    assert embed["color"] == 0xF1C40F
    assert embed["description"] == (
        "**Alpha** put up **30.0**, the week's high. "
        "**QB A1** (Alpha) was the top starter with **30.0** (+10.0 VOR)."
    )
    names = [field["name"] for field in embed["fields"]]
    assert names == ["Records & milestones", "Bracket"]
    assert "Alpha — 30.0 pts (Most points, game, #1)" in embed["fields"][0]["value"]
    assert "Alpha beat Gamma for the first time ever (series now 1-1-0)" in embed["fields"][0]["value"]
    assert embed["fields"][1]["value"] == "Final: Alpha 30.0, Gamma 20.0"
    assert embed["footer"] == {"text": f"Full records: {SITE} · through Week 4"}
    assert embed_length(embed) < 6000


def test_regular_season_recap_has_the_playoff_picture(tables):
    league, book = tables
    facts = milestones.recap_facts(league, book, (2020, 2))
    embed = recap.recap_embed(facts, SITE)
    names = [field["name"] for field in embed["fields"]]
    assert "Playoff picture" in names and "Bracket" not in names
    picture = next(f for f in embed["fields"] if f["name"] == "Playoff picture")
    assert picture["value"].startswith("1. Gamma 2-0-0\n2. Alpha 1-1-0")


def test_quiet_week_has_no_records_field():
    facts = milestones.RecapFacts(2020, 9, False, ("Alpha", 101.5), ("QB A1", "Alpha", 20.0, 3.0), (), (), (), ("1. Alpha 5-4-0",), ())
    embed = recap.recap_embed(facts, SITE)
    assert [f["name"] for f in embed["fields"]] == ["Playoff picture"]


def test_markdown_in_names_is_escaped():
    facts = milestones.RecapFacts(2020, 1, False, ("Team_*Underscore*", 90.0), ("A_B", "C*D", 10.0, 1.0), ("Team_*Underscore* — 90.0 pts (Most points, game, #7)",), (), (), (), ())
    embed = recap.recap_embed(facts, SITE)
    assert "**Team\\_\\*Underscore\\***" in embed["description"]
    assert embed["fields"][0]["value"].startswith("Team\\_\\*Underscore\\*")


def test_fit_lines_drops_whole_lines_and_counts_the_rest():
    lines = [f"line {i} " + "x" * 290 for i in range(5)]  # about 300 characters each
    text = recap.fit_lines(lines, MAX_FIELD_VALUE)
    assert text.startswith("line 0") and "line 2" in text and "line 3" not in text
    assert text.endswith("…and 2 more")
    assert len(text) <= MAX_FIELD_VALUE
    assert recap.fit_lines(["short", "lines"], MAX_FIELD_VALUE) == "short\nlines"
    assert recap.fit_lines([], MAX_FIELD_VALUE) == ""
    long = recap.fit_lines(["y" * 2000, "z"], 100)
    assert len(long) <= 100 and long.endswith("…and 1 more")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_recap.py -v`
Expected: collection error or `NotImplementedError`, depending on whether Task 1 left a stub.

- [ ] **Step 3: Implement**

`hof/discord/recap.py`:

```python
"""The Tuesday recap: one embed from the week's RecapFacts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from bdfl.messages import MAX_DESCRIPTION, MAX_FIELD_VALUE, escape_markdown, truncate
from hof.stats.milestones import RecapFacts

RECAP_COLOR = 0xF1C40F
NOTE_ROOM = 24  # room for "\n…and 999 more"


def fit_lines(lines: Sequence[str], limit: int) -> str:
    """Join lines with newlines inside `limit`, dropping whole lines from the end and saying how many."""
    kept: list[str] = []
    length = 0
    for index, line in enumerate(lines):
        extra = len(line) + (1 if kept else 0)
        if length + extra > limit - NOTE_ROOM:
            remaining = len(lines) - index
            if not kept:
                head = truncate(line, limit - NOTE_ROOM)
                return head + (f"\n…and {remaining - 1} more" if remaining > 1 else "")
            return "\n".join(kept) + f"\n…and {remaining} more"
        kept.append(line)
        length += extra
    return "\n".join(kept)


def _field(name: str, lines: Sequence[str]) -> dict[str, str]:
    return {"name": name, "value": fit_lines([escape_markdown(line) for line in lines], MAX_FIELD_VALUE)}


def recap_embed(facts: RecapFacts, site_url: str) -> dict[str, Any]:
    sentences: list[str] = []
    if facts.high_score is not None:
        name, score = facts.high_score
        sentences.append(f"**{escape_markdown(name)}** put up **{score:.1f}**, the week's high.")
    if facts.top_starter is not None:
        player, franchise, points, vor = facts.top_starter
        sentences.append(
            f"**{escape_markdown(player)}** ({escape_markdown(franchise)}) was the top starter "
            f"with **{points:.1f}** ({vor:+.1f} VOR)."
        )
    if not sentences:
        sentences.append("No counted games this week.")
    fields: list[dict[str, str]] = []
    notes = list(facts.new_records) + list(facts.milestones) + list(facts.series_firsts)
    if notes:
        fields.append(_field("Records & milestones", notes))
    if facts.playoff_picture:
        fields.append(_field("Playoff picture", facts.playoff_picture))
    if facts.bracket:
        fields.append(_field("Bracket", facts.bracket))
    return {
        "title": f"📜 Week {facts.week} in the record books",
        "color": RECAP_COLOR,
        "description": truncate(" ".join(sentences), MAX_DESCRIPTION),
        "fields": fields,
        "footer": {"text": f"Full records: {site_url} · through Week {facts.week}"},
    }
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/hof/test_hof_recap.py -v`
Expected: 5 passed. Check `bdfl.messages.escape_markdown` escapes `_` and `*` with a backslash (it does: the pattern is `[\\*_~`|>\[\]]`); if the escaped-name assertion fails on the exact backslashes, print the description and match the test to what the notifier's escaper produces, since both posts must escape the same way.

- [ ] **Step 5: Lint and commit**

Run: `ruff check hof tests/hof`
Expected: no issues.

```bash
git add hof/discord/recap.py tests/hof/test_hof_recap.py
git commit -m "feat(hof): weekly recap embed

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: The season wrap embed

**Files:**
- Create: `hof/discord/wrap.py`
- Test: `tests/hof/test_hof_wrap.py`

- [ ] **Step 1: Write the failing tests**

`tests/hof/test_hof_wrap.py`:

```python
import pytest
from synthetic import four_team_league

from bdfl.messages import embed_length
from hof.config import HallRules
from hof.discord import wrap
from hof.stats import milestones
from hof.stats.model import compute

SITE = "https://example.test/hof/"


@pytest.fixture(scope="module")
def model():
    return compute(four_team_league().seasons, HallRules(player_min_vor=30, player_min_starts=3, franchise_min_titles=1))


def test_wrap_embed_for_2020(model):
    awards = milestones.season_awards(model.league, model.records, 2020)
    embed = wrap.wrap_embed(model, 2020, awards, SITE)
    assert embed["title"] == "🏆 2020 season wrap"
    assert embed["color"] == 0xE5B80B
    assert embed["description"] == (
        "**Alpha** wins its 1st title, **30.0–20.0** over **Gamma**. "
        "Regular season 1-1-0, 32.0 points, the 2nd-highest season ever."
    )
    awards_field, hall_field = embed["fields"]
    assert awards_field["name"] == "Season awards"
    assert awards_field["value"].splitlines() == [
        "**Top starter:** QB A1, 87.0 pts (Alpha)",
        "**Best value over replacement:** QB A1, +36.0 VOR (Alpha)",
        "**Best lineup manager:** Alpha, 100.0% of optimal",
        "**Most points left on the bench:** Beta, 4.0",
    ]
    assert hall_field["name"] == "🏛 Hall of Fame · Class of 2020"
    assert hall_field["value"].splitlines() == [
        "**QB A1** (QB) · 5 starts, 97.0 pts, +41.0 VOR, 1 title as a starter",
        "**Alpha Prime** · 1 title",
    ]
    assert embed["footer"] == {"text": f"Full records: {SITE}"}
    assert embed_length(embed) < 6000


def test_wrap_without_inductees_or_final(model):
    awards = milestones.season_awards(model.league, model.records, 2021)
    embed = wrap.wrap_embed(model, 2021, awards, SITE)
    assert embed["description"] == "The season has no final yet."
    hall_field = embed["fields"][-1]
    assert hall_field["value"] == "No new inductees."
```

The value-over-replacement numbers (36.0 for the 2020 season, 41.0 career) are the four-team league's QB A1 under the two-thirds baseline, as documented in `tests/hof/test_hof_franchises.py`; read them from there if they differ.

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_wrap.py -v`
Expected: 2 failures.

- [ ] **Step 3: Implement**

`hof/discord/wrap.py`:

```python
"""The season wrap: one embed with the champion, the awards, and the new Hall of Fame class."""

from __future__ import annotations

from typing import Any

from bdfl.messages import MAX_DESCRIPTION, MAX_FIELD_VALUE, escape_markdown, truncate
from hof.discord.recap import fit_lines
from hof.stats.milestones import SeasonAwards, ordinal
from hof.stats.model import Model

WRAP_COLOR = 0xE5B80B


def _name(text: str) -> str:
    return escape_markdown(text)


def champion_sentence(model: Model, year: int) -> str | None:
    season = model.league.season(year)
    final = season.final
    if final is None or final.winner is None or final.loser is None:
        return None
    champion, runner_up = final.winner.franchise_id, final.loser.franchise_id
    titles = sum(1 for y, c, _ in model.champions if c == champion and y <= year)
    return (
        f"**{_name(model.league.name_in(champion, year))}** wins its {ordinal(titles)} title, "
        f"**{final.winner.score or 0.0:.1f}–{final.loser.score or 0.0:.1f}** over "
        f"**{_name(model.league.name_in(runner_up, year))}**."
    )


def record_sentence(awards: SeasonAwards) -> str | None:
    if awards.champion is None:
        return None
    _, record, points_for, rank = awards.champion
    text = f"Regular season {record}, {points_for:.1f} points"
    if rank is not None:
        text += f", the {ordinal(rank)}-highest season ever"
    return text + "."


def awards_lines(awards: SeasonAwards) -> list[str]:
    lines: list[str] = []
    if awards.top_scorer is not None:
        player, franchise, points = awards.top_scorer
        lines.append(f"**Top starter:** {_name(player)}, {points:.1f} pts ({_name(franchise)})")
    if awards.best_vor is not None:
        player, franchise, vor = awards.best_vor
        lines.append(f"**Best value over replacement:** {_name(player)}, {vor:+.1f} VOR ({_name(franchise)})")
    if awards.best_manager is not None:
        franchise, efficiency = awards.best_manager
        lines.append(f"**Best lineup manager:** {_name(franchise)}, {efficiency * 100:.1f}% of optimal")
    if awards.most_bench_left is not None:
        franchise, points = awards.most_bench_left
        lines.append(f"**Most points left on the bench:** {_name(franchise)}, {points:.1f}")
    return lines


def hall_lines(model: Model, year: int) -> list[str]:
    lines = [
        f"**{_name(p.name)}** ({p.position}) · {p.starts} starts, {p.points:.1f} pts, {p.vor:+.1f} VOR, "
        f"{p.titles} title{'s' if p.titles != 1 else ''} as a starter"
        for p in model.hall.players
        if p.class_year == year
    ]
    lines += [
        f"**{_name(f.name)}** · {f.titles} title{'s' if f.titles != 1 else ''}"
        for f in model.hall.franchises
        if f.class_year == year
    ]
    return lines or ["No new inductees."]


def wrap_embed(model: Model, year: int, awards: SeasonAwards, site_url: str) -> dict[str, Any]:
    sentences = [s for s in (champion_sentence(model, year), record_sentence(awards)) if s]
    description = " ".join(sentences) if sentences else "The season has no final yet."
    fields = []
    lines = awards_lines(awards)
    if lines:
        fields.append({"name": "Season awards", "value": fit_lines(lines, MAX_FIELD_VALUE)})
    fields.append({"name": f"🏛 Hall of Fame · Class of {year}", "value": fit_lines(hall_lines(model, year), MAX_FIELD_VALUE)})
    return {
        "title": f"🏆 {year} season wrap",
        "color": WRAP_COLOR,
        "description": truncate(description, MAX_DESCRIPTION),
        "fields": fields,
        "footer": {"text": f"Full records: {site_url}"},
    }
```

- [ ] **Step 4: Run all three Discord test files**

Run: `pytest tests/hof/test_hof_wrap.py tests/hof/test_hof_recap.py tests/hof/test_hof_notify.py -v`
Expected: all pass, including the `run_*` tests from Task 1 now that both embed builders exist.

- [ ] **Step 5: Lint and commit**

Run: `ruff check hof tests/hof`
Expected: no issues.

```bash
git add hof/discord/wrap.py tests/hof/test_hof_wrap.py
git commit -m "feat(hof): season wrap embed

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: The `notify` command and a preview against real seasons

**Files:**
- Modify: `hof/__main__.py`
- Test: `tests/hof/test_hof_cli.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/hof/test_hof_cli.py`:

```python
def test_notify_dry_run_prints_an_embed(tmp_path, fixtures_dir, capsys):
    code = cli.main(["--data", str(fixtures_dir), "--config", str(CONFIG), "notify", "--dry-run", "--year", "2020", "--week", "16"])
    assert code == 0
    out = capsys.readouterr().out
    assert '"title": "🏆 2020 season wrap"' in out
    assert "Marcus Peters' Peter Peckers" in out


def test_notify_without_a_webhook_url_fails_clearly(tmp_path, fixtures_dir, monkeypatch, capsys):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    code = cli.main(["--data", str(fixtures_dir), "--config", str(CONFIG), "notify", "--year", "2020", "--week", "16"])
    assert code == 1
    assert "DISCORD_WEBHOOK_URL" in capsys.readouterr().err
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_cli.py -v`
Expected: 2 failures, `argparse` rejecting `notify`.

- [ ] **Step 3: Implement**

In `hof/__main__.py`, add the imports:

```python
import os

from bdfl.discord import DiscordWebhook
from hof.discord import notify
```

add a subparser after `build`:

```python
    notify_parser = commands.add_parser("notify", help="post the newest complete week's recap or the season wrap to Discord")
    notify_parser.add_argument("--dry-run", action="store_true", help="print the embed instead of posting; touches nothing")
    notify_parser.add_argument("--year", type=int, help="with --week: build this week regardless of completion or state")
    notify_parser.add_argument("--week", type=int)
```

and handle it before `return 2`:

```python
    if args.command == "notify":
        if (args.year is None) != (args.week is None):
            parser.error("--year and --week go together")
        force = (args.year, args.week) if args.year is not None else None
        model = compute(load_all(args.data), config.hall)
        state_path = args.data / "notify-state.json"
        if args.dry_run:
            outcome = notify.run(model, config.site_base_url, state_path, notify.now_utc(), None, dry_run=True, force=force)
        else:
            try:
                url = notify.webhook_url(os.environ)
            except notify.NotifyError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            outcome = notify.run(model, config.site_base_url, state_path, notify.now_utc(), DiscordWebhook(url), force=force)
        print(f"{'posted' if outcome.posted else 'nothing posted'}: {outcome.reason}"
              + (f" ({outcome.decision.kind} {outcome.decision.year} week {outcome.decision.week})" if outcome.decision else ""))
        return 0
```

Update the module docstring to `{fetch,stats,build,notify}`.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/hof/test_hof_cli.py -v`
Expected: all pass (the two new ones plus the earlier ones).

- [ ] **Step 5: Preview real posts and read them**

These use the real backfill and touch nothing:

```bash
python -m hof notify --dry-run --year 2025 --week 9
python -m hof notify --dry-run --year 2025 --week 15
python -m hof notify --dry-run --year 2025 --week 17
```

Expected: a regular-season recap with a playoff picture, a playoff-week recap with a bracket, and the 2025 season wrap naming The Youth Academy as champion with a Hall of Fame class. Read every line as a league member would. Things to fix if they appear: a franchise id anywhere, a sentence with a missing name, a field value longer than 1024 characters (the builder must have capped it), or a "…and N more" on a normal week (raise `NOTE_ROOM` or shorten the sentences in `hof/stats/milestones.py`, then fix the tests that pin the wording). Paste the three embeds into the commit body of the next step so the owner sees them in the PR.

- [ ] **Step 6: Lint and commit**

Run: `ruff check src tests scripts hof && pytest`
Expected: no lint issues; every test passes.

```bash
git add hof/__main__.py tests/hof/test_hof_cli.py
git commit -m "feat(hof): notify command with dry-run previews

<the three preview embeds>

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Workflow, README, and rollout

**Files:**
- Modify: `.github/workflows/hof.yml`, `README.md`

- [ ] **Step 1: Harden the checkout and the snapshot push**

A re-run of a failed job checks out the commit that triggered it, which predates the workflow's own snapshot commit, so its push is rejected. In `.github/workflows/hof.yml`, change the checkout step to:

```yaml
      # Always start from the tip of main, not the triggering commit: a re-run of a failed job
      # would otherwise check out a base that predates this workflow's own snapshot commit and
      # its push would be rejected as non-fast-forward.
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
        with:
          ref: main
```

and in the "Commit refreshed snapshots" step insert `git pull --rebase origin main` on the line before `git push`, with the comment `# Someone may have merged to main while MFL was being fetched; replay on top of it.`

- [ ] **Step 2: Add the notify step and the state commit**

Append after the `deploy-pages` step:

```yaml
      # Off until the owner sets the repository variable HOF_NOTIFY to "true" (Settings, Secrets
      # and variables, Actions, Variables) and adds the DISCORD_WEBHOOK_URL secret.
      - name: Post the weekly recap or season wrap to Discord
        if: vars.HOF_NOTIFY == 'true'
        env:
          DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
        run: python -m hof notify

      - name: Commit the notify state
        if: vars.HOF_NOTIFY == 'true'
        run: |
          git add data/notify-state.json
          if git diff --cached --quiet; then
            echo "no state change"
          else
            git config user.name 'github-actions[bot]'
            git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
            git commit -m "data: notify state $(date -u +%F)"
            git pull --rebase origin main
            git push
          fi
```

Check the YAML parses: `ruby -ryaml -e 'YAML.load_file(".github/workflows/hof.yml"); puts "ok"'`
Expected: `ok`.

- [ ] **Step 3: Document it**

In `README.md`, under "Hall of Records", after the "Publishing" subsection, add:

````markdown
### Discord posts

The same workflow posts to the league channel through the notifier's webhook: a recap every Tuesday of a completed week (high score, top starter, new records and milestones, series firsts, the playoff picture or the bracket) and a season wrap after the final (champion, season awards, the new Hall of Fame class). A week counts as complete forty hours after MFL's Sunday lineup lock, once every matchup is scored. `data/notify-state.json` records the last post so a re-run never posts a week twice.

One-time setup: add the repository secret `DISCORD_WEBHOOK_URL` (the same URL as the SSM parameter), then set the repository variable `HOF_NOTIFY` to `true`. Set it to anything else to pause posting without touching the workflow.

Preview a post without sending it:

```bash
python -m hof notify --dry-run --year 2025 --week 9
```
````

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/hof.yml README.md
git commit -m "ci(hof): Discord notify step, state commit, and re-run hardening

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Rollout (owner steps after the PR merges)

1. Repository settings, Secrets and variables, Actions: add the secret `DISCORD_WEBHOOK_URL` with the channel webhook URL. It is the same URL stored in SSM for the notifier; copy it from Discord (channel settings, Integrations, Webhooks) rather than from AWS.
2. In the same place, under Variables, add `HOF_NOTIFY` = `true`.
3. Nothing posts until a week is complete. The 2026 season's first lock fires on the first Sunday of games; the first recap goes out the Tuesday after at 11:00 UTC. To see one sooner, run `python -m hof notify --dry-run --year 2025 --week 9` locally, or, to send a real test post, run `DISCORD_WEBHOOK_URL=... python -m hof notify --year 2025 --week 9` once from your machine: a forced week never writes the state file, so it cannot interfere with the schedule.
4. If a Tuesday post fails, the workflow run fails and GitHub emails you; the state file is untouched, so the next successful run posts that week (or a newer one, never both).

That completes the four plans. What remains outside them: the curated Hall of Fame overlay and slash commands, both listed as out of scope in the spec.
