# Analytics Layer, Plan 3 of 3: Discord

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Post the week's awards and power rankings as a second embed in the Tuesday recap message, and add the awards leader, luckiest and unluckiest franchises, and the final power ranking to the season wrap.

**Architecture:** A new `analytics_embed()` in `hof/discord/recap.py` renders one `WeekAnalytics` from Plan 1's model; `wrap.py` gains `analytics_lines()`; `notify.build_embed()` becomes `build_embeds()` returning a list that the existing webhook client posts as one message. No change to the completion rule, state file, or workflow.

**Tech Stack:** Python 3.13, pytest. Run from the repo root with the project venv active.

**Spec:** `docs/superpowers/specs/2026-09-08-analytics-layer-design.md`, section 5. **Prerequisite:** Plan 1 merged (`Model.analytics`, `hof.stats.awards.format_value`, `hof.stats.power.movement_label` from Plan 2 Task 1). If Plan 2 has not landed yet, add `movement_label` to `hof/stats/power.py` exactly as Plan 2 Task 1 specifies before starting.

**Conventions:** Discord text goes through `bdfl.messages.escape_markdown` for every name, label, and detail, but never for the `**` that the embed itself adds. Lines are joined with `recap.fit_lines` so a field never exceeds 1,024 characters. Golden tests compare whole lines.

**Synthetic values used by the tests** (from Plan 1): 2020 week 2 awards are Gamma 18.0 high, Beta 9.0 low, Gamma blowout by 6.0 over Alpha, Delta closest by 2.0 over Beta, Gamma best lineup at 100%, Gamma 0.0 left on the bench, Delta luckiest win at 11.0 (all-play 1-2-0), Alpha unluckiest loss at 12.0 (2-1-0). Week 2 power ranking: Gamma 0.883 ▲1, Alpha 0.733 ▼1, Delta 0.267 ▲1, Beta 0.117 ▼1. Week 4 is the Final (playoff). Season: awards leader Alpha with 15, luckiest Delta +0.7, unluckiest Alpha −0.7, final power number one Gamma 0.883.

---

### Task 1: The awards and power rankings embed

**Files:**
- Modify: `hof/discord/recap.py`
- Test: `tests/hof/test_hof_recap.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/hof/test_hof_recap.py` (add `from hof.stats import analytics` and `from hof.stats.awards import Award` and `from hof.stats.power import PowerLine` to the imports):

```python
@pytest.fixture(scope="module")
def season_2020():
    league = four_team_league()
    return analytics.season_analytics(league, league.season(2020))


def test_analytics_embed_for_a_regular_season_week(season_2020):
    embed = recap.analytics_embed(season_2020, 2, SITE)
    assert embed["title"] == "🏅 Week 2 awards and power rankings"
    assert embed["color"] == 0x3498DB
    awards_field, power_field = embed["fields"]
    assert awards_field["name"] == "Awards"
    assert awards_field["value"].splitlines() == [
        "**Highest score:** Gamma, 18.0 (beat Alpha 18.0–12.0)",
        "**Lowest score:** Beta, 9.0 (lost to Delta 9.0–11.0)",
        "**Biggest blowout:** Gamma, 6.0 (over Alpha, 18.0–12.0)",
        "**Closest game:** Delta, 2.0 (over Beta, 11.0–9.0)",
        "**Best lineup:** Gamma, 100.0% (18.0 of 18.0 possible)",
        "**Most points left on the bench:** Gamma, 0.0 (18.0 of 18.0 possible)",
        "**Luckiest win:** Delta, 11.0 (would have gone 1-2-0 against the field)",
        "**Unluckiest loss:** Alpha, 12.0 (would have gone 2-1-0 against the field)",
    ]
    assert power_field["name"] == "Power rankings"
    assert power_field["value"].splitlines() == [
        "1. ▲1 Gamma · 0.883",
        "2. ▼1 Alpha · 0.733",
        "3. ▲1 Delta · 0.267",
        "4. ▼1 Beta · 0.117",
    ]
    assert embed["footer"] == {"text": f"Season page: {SITE}seasons/2020/"}
    assert embed_length(embed) < 6000


def test_first_ranked_week_says_new(season_2020):
    embed = recap.analytics_embed(season_2020, 1, SITE)
    assert embed["fields"][1]["value"].splitlines()[0] == "1. new Alpha · 1.000"


def test_analytics_embed_in_a_playoff_week_has_awards_only(season_2020):
    embed = recap.analytics_embed(season_2020, 4, SITE)
    assert embed["title"] == "🏅 Week 4 awards"
    assert [field["name"] for field in embed["fields"]] == ["Awards"]
    lines = embed["fields"][0]["value"].splitlines()
    assert lines[0] == "**Highest score:** Alpha, 30.0 (beat Gamma 30.0–20.0)"
    assert "**Luckiest win:** Alpha, 30.0" in lines  # no all-play detail in the playoffs


def test_analytics_embed_is_none_without_a_week(season_2020):
    assert recap.analytics_embed(season_2020, 9, SITE) is None


def test_analytics_lines_escape_markdown():
    award = Award("high_score", "High_score", "0001", "Team_*X*", "0001", 20.0, "pts", "beat [Y] 20.0–1.0")
    assert recap.award_line(award) == "**High\\_score:** Team\\_\\*X\\*, 20.0 (beat \\[Y\\] 20.0–1.0)"
    line = PowerLine(1, "0001", "Team_*X*", 0.9, 0.9, 1.0, 0.8, 3)
    assert recap.power_line(line) == "1. ▲2 Team\\_\\*X\\* · 0.900"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/hof/test_hof_recap.py -v`
Expected: the five new tests FAIL with `AttributeError: module 'hof.discord.recap' has no attribute 'analytics_embed'` (or `award_line`)

- [ ] **Step 3: Implement**

In `hof/discord/recap.py`, add the imports:

```python
from hof.stats.analytics import SeasonAnalytics
from hof.stats.awards import Award, format_value
from hof.stats.power import PowerLine, movement_label
```

add the constant after `RECAP_COLOR`:

```python
ANALYTICS_COLOR = 0x3498DB
```

and append:

```python
def award_line(award: Award) -> str:
    line = f"**{escape_markdown(award.label)}:** {escape_markdown(award.holder_name)}, {format_value(award.value, award.unit)}"
    if award.detail:
        line += f" ({escape_markdown(award.detail)})"
    return line


def power_line(line: PowerLine) -> str:
    return f"{line.rank}. {movement_label(line.movement)} {escape_markdown(line.name)} · {line.score:.3f}"


def analytics_embed(stats: SeasonAnalytics, week: int, site_url: str) -> dict[str, Any] | None:
    """The second embed of a Tuesday message: the week's awards, then the power rankings in
    regular-season weeks. None when the week has nothing to say."""
    facts = next((w for w in stats.weeks if w.week == week), None)
    if facts is None:
        return None
    fields: list[dict[str, str]] = []
    if facts.awards:
        fields.append({"name": "Awards", "value": fit_lines([award_line(a) for a in facts.awards], MAX_FIELD_VALUE)})
    if facts.power:
        fields.append({"name": "Power rankings", "value": fit_lines([power_line(p) for p in facts.power], MAX_FIELD_VALUE)})
    if not fields:
        return None
    suffix = "" if facts.playoff else " and power rankings"
    return {
        "title": f"🏅 Week {week} awards{suffix}",
        "color": ANALYTICS_COLOR,
        "fields": fields,
        "footer": {"text": f"Season page: {site_url}seasons/{stats.year}/"},
    }
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/hof/test_hof_recap.py -v`
Expected: all passed

- [ ] **Step 5: Lint and commit**

```bash
ruff check hof tests && git add hof/discord/recap.py tests/hof/test_hof_recap.py && git commit -m "hof discord: awards and power rankings embed"
```

---

### Task 2: Season wrap lines

**Files:**
- Modify: `hof/discord/wrap.py`
- Test: `tests/hof/test_hof_wrap.py`

- [ ] **Step 1: Update the golden test**

In `tests/hof/test_hof_wrap.py`, `test_wrap_embed_for_2020`, extend the expected awards lines to:

```python
    assert awards_field["value"].splitlines() == [
        "**Top starter:** QB A1, 87.0 pts (Alpha)",
        "**Best value over replacement:** QB A1, +36.0 VOR (Alpha)",
        "**Best lineup manager:** Alpha, 100.0% of optimal",
        "**Most points left on the bench:** Beta, 4.0",
        "**Awards leader:** Alpha, 15 awards",
        "**Luckiest:** Delta, +0.7",
        "**Unluckiest:** Alpha, -0.7",
        "**Final power ranking:** #1 Gamma, 0.883",
    ]
```

and append to `test_wrap_without_inductees_or_final`:

```python
    awards_field = embed["fields"][0]
    assert awards_field["name"] == "Season awards"
    assert "**Awards leader:** Alpha Prime, 6 awards" in awards_field["value"]
    assert "**Final power ranking:** #1 Alpha Prime, 1.000" in awards_field["value"]
```

Add a test for the escaping and the empty case:

```python
def test_analytics_lines_escape_names_and_skip_missing_seasons(model):
    assert wrap.analytics_lines(model, 1999) == []
    lines = wrap.analytics_lines(model, 2020)
    assert lines[0] == "**Awards leader:** Alpha, 15 awards"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/hof/test_hof_wrap.py -v`
Expected: 3 failed

- [ ] **Step 3: Implement**

In `hof/discord/wrap.py`, append after `awards_lines`:

```python
def analytics_lines(model: Model, year: int) -> list[str]:
    """Awards leader, luckiest and unluckiest, and the final power ranking; empty when unknown."""
    stats = model.analytics.get(year)
    if stats is None:
        return []
    lines: list[str] = []
    if stats.awards_leaders:
        names = ", ".join(_name(model.league.name_in(fid, year)) for fid in stats.awards_leaders)
        plural = "" if stats.awards_leader_count == 1 else "s"
        lines.append(f"**Awards leader:** {names}, {stats.awards_leader_count} award{plural}")
    if stats.luckiest is not None:
        lines.append(f"**Luckiest:** {_name(stats.luckiest.name)}, {stats.luckiest.luck:+.1f}")
    if stats.unluckiest is not None:
        lines.append(f"**Unluckiest:** {_name(stats.unluckiest.name)}, {stats.unluckiest.luck:+.1f}")
    if stats.final_power:
        top = stats.final_power[0]
        lines.append(f"**Final power ranking:** #1 {_name(top.name)}, {top.score:.3f}")
    return lines
```

In `wrap_embed`, change `lines = awards_lines(awards)` to:

```python
    lines = awards_lines(awards) + analytics_lines(model, year)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/hof/test_hof_wrap.py -v`
Expected: all passed

- [ ] **Step 5: Lint and commit**

```bash
ruff check hof tests && git add hof/discord/wrap.py tests/hof/test_hof_wrap.py && git commit -m "hof discord: awards leader, luck, and final power ranking in the season wrap"
```

---

### Task 3: Post two embeds in one message

**Files:**
- Modify: `hof/discord/notify.py` (`build_embed` → `build_embeds`, `run`)
- Modify: `hof/__main__.py` (the `--dry-run` help text)
- Test: `tests/hof/test_hof_notify.py`, `tests/hof/test_hof_cli.py`

- [ ] **Step 1: Update and add the failing tests**

In `tests/hof/test_hof_notify.py`:

- In `test_run_posts_once_and_records_state`, replace `assert len(posted) == 1 and posted[0][0]["title"] == "📜 Week 3 in the record books"` with:

  ```python
      assert len(posted) == 1
      assert [e["title"] for e in posted[0]] == ["📜 Week 3 in the record books", "🏅 Week 3 awards"]  # week 3 is a playoff week
  ```

- In `test_run_dry_run_prints_without_posting_or_saving`, change `json.loads(out)["title"]` to `json.loads(out)[0]["title"]`.
- In `test_run_forced_week_ignores_state`, change `json.loads(capsys.readouterr().out)["title"]` to `json.loads(capsys.readouterr().out)[0]["title"]`.
- Add `from bdfl.messages import embed_length` and `from hof.snapshots import load_season` to the imports, and append:

```python
def test_build_embeds_pairs_the_recap_with_awards_and_rankings():
    model = compute(league_with_locks().seasons, RULES)
    embeds = notify.build_embeds(model, Decision("recap", 2020, 2), "https://example.test/")
    assert [e["title"] for e in embeds] == ["📜 Week 2 in the record books", "🏅 Week 2 awards and power rankings"]
    assert embeds[1]["footer"] == {"text": "Season page: https://example.test/seasons/2020/"}
    assert sum(embed_length(e) for e in embeds) < 6000
    wrap_only = notify.build_embeds(model, Decision("wrap", 2020, 4), "https://example.test/")
    assert [e["title"] for e in wrap_only] == ["🏆 2020 season wrap"]


def test_a_real_week_fits_in_one_message(fixtures_dir):
    model = compute([load_season(fixtures_dir / "raw" / "2020")], RULES)
    embeds = notify.build_embeds(model, Decision("recap", 2020, 13), "https://example.test/")
    assert len(embeds) == 2
    assert sum(embed_length(e) for e in embeds) < 6000
    assert len(embeds[1]["fields"][1]["value"].splitlines()) == 12
```

In `tests/hof/test_hof_cli.py`, append:

```python
def test_notify_dry_run_prints_the_awards_embed_too(tmp_path, fixtures_dir, capsys):
    code = cli.main(["--data", str(fixtures_dir), "--config", str(CONFIG), "notify", "--dry-run", "--year", "2020", "--week", "13"])
    assert code == 0
    out = capsys.readouterr().out
    assert '"title": "📜 Week 13 in the record books"' in out
    assert '"title": "🏅 Week 13 awards and power rankings"' in out
    assert '"name": "Power rankings"' in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/hof/test_hof_notify.py tests/hof/test_hof_cli.py -v`
Expected: the changed and new tests FAIL (`build_embeds` missing; dry-run output is a dict, not a list)

- [ ] **Step 3: Implement**

In `hof/discord/notify.py`, change the recap import to:

```python
from hof.discord.recap import analytics_embed, recap_embed
```

Replace `build_embed` with:

```python
def build_embeds(model: Model, decision: Decision, site_url: str) -> list[dict[str, Any]]:
    """One message: the wrap embed alone, or the recap embed followed by the week's awards and
    power rankings when the week has them."""
    if decision.kind == "wrap":
        awards = milestones.season_awards(model.league, model.records, decision.year)
        return [wrap_embed(model, decision.year, awards, site_url)]
    facts = milestones.recap_facts(model.league, model.records, (decision.year, decision.week))
    embeds = [recap_embed(facts, site_url)]
    stats = model.analytics.get(decision.year)
    extra = analytics_embed(stats, decision.week, site_url) if stats is not None else None
    if extra is not None:
        embeds.append(extra)
    return embeds
```

In `run()`, replace the three lines from `embed = build_embed(...)` through `webhook.post([embed])` so they read:

```python
    embeds = build_embeds(model, decision, site_url)
    if dry_run:
        print(json.dumps(embeds, ensure_ascii=False, indent=2))
        return Outcome(False, decision, "dry run")
    if webhook is None:
        raise NotifyError("no webhook to post with")
    webhook.post(embeds)
```

Update the docstring's first sentence to "Post the newest complete week once. With dry_run, print the embeds instead; ...".

In `hof/__main__.py`, change the `--dry-run` help to `"print the embeds instead of posting; touches nothing"`.

- [ ] **Step 4: Run the whole suite**

Run: `pytest && ruff check hof tests scripts src`
Expected: all passed, clean lint.

- [ ] **Step 5: Commit**

```bash
git add hof/discord/notify.py hof/__main__.py tests/hof/test_hof_notify.py tests/hof/test_hof_cli.py && git commit -m "hof discord: post the recap and the analytics embed as one message"
```

---

### Task 4: README

**Files:**
- Modify: `README.md` (the Hall of Records section)

- [ ] **Step 1: Describe the new surfaces**

In `README.md`, replace the first paragraph of the "Hall of Records" section with:

```markdown
`hof/` builds the league's records site from MFL history: every player's career as a BDFL starter, franchise histories, head-to-head series and a rivalry grid, season pages with standings, all-play records, luck, power rankings, and weekly awards, a records book, a rule-based Hall of Fame, draft hindsight, and a trade ledger. Design: `docs/superpowers/specs/2026-09-06-hall-of-records-design.md` and `docs/superpowers/specs/2026-09-08-analytics-layer-design.md`.

The Tuesday Discord message carries two embeds: the week in the record books, then the week's awards and power rankings. Award names can be renamed in `data/config.toml` under `[awards]` (the keys are listed in `hof/stats/awards.py`).
```

- [ ] **Step 2: Commit**

```bash
git add README.md && git commit -m "docs: analytics layer in the README"
```

---

### Task 5: Dry run against the real data

**Files:** none.

- [ ] **Step 1: Print the newest complete week's message**

Run: `python -m hof notify --dry-run` (prints nothing to post outside the season, so instead force the newest played week, for example `python -m hof notify --dry-run --year 2026 --week 1`).

Expected: a JSON list of two embeds. The second has title `🏅 Week 1 awards and power rankings`, an `Awards` field with nine lines, and a `Power rankings` field with twelve lines ending in three-decimal scores, and a footer pointing at `https://btcookies.github.io/bdfl-trade-notifier/seasons/2026/`.

- [ ] **Step 2: Confirm the message fits Discord's limit**

```bash
PYTHONPATH=src python -m hof notify --dry-run --year 2026 --week 1 | PYTHONPATH=src python -c "import json, sys; from bdfl.messages import embed_length; e = json.load(sys.stdin); print(len(e), 'embeds,', sum(embed_length(x) for x in e), 'chars')"
```

Expected: `2 embeds, N chars` with N under 6000.

- [ ] **Step 3: Nothing to commit**

The dry run touches no files.

---

## Done when

- `pytest` passes and `ruff check hof tests scripts src` is clean.
- A recap decision produces two embeds and a wrap decision one; the dry run prints a list.
- The wrap's "Season awards" field ends with the awards leader, luckiest, unluckiest, and final power ranking lines.
- The README describes the season pages, the rivalry grid, the second embed, and the `[awards]` table.

After this plan, the next scheduled Tuesday run posts the two-embed message with no workflow or secret changes.
