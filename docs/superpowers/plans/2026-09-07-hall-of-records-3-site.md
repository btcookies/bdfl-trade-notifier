# Hall of Records, Plan 3 of 4: Site and Workflow

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the `Model` from Plan 2 into the static site described in the spec, and add the GitHub Actions workflow that refetches, commits snapshots, builds, and deploys it to GitHub Pages every Tuesday of the season.

**Architecture:** `hof/site/build.py` turns a `Model` into a directory of HTML using Jinja2 templates in `hof/site/templates/` and two static assets. Every page is a function that returns `(relative path, html)` pairs; `build_site()` runs them all. One workflow file drives fetch, data commit, build, and Pages deploy. The Discord `notify` step is Plan 4.

**Tech Stack:** Python 3.13, Jinja2 3.1 (already in `hof/requirements.txt`), plain CSS and about sixty lines of vanilla JavaScript, GitHub Actions with GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-09-06-hall-of-records-design.md`, sections 7 and 9.

---

## What Plans 1 and 2 give you

`hof.stats.model.compute(seasons, rules) -> Model` with these fields, all already computed:

- `league: League` with `seasons`, `latest`, `franchise_ids()`, `current_name(id)`, `name_in(id, year)`, `eras(id) -> [Era(franchise_id, name, first_year, last_year)]`, `player_info(id)`.
- `careers: dict[str, Career]`; `Career` has `player_id, name, position, first_year, last_year, active, seasons: (SeasonLine,...), stints: (Stint,...), moves: (Move,...), starts, points, vor, bench_points, playoff_starts, playoff_points, titles, franchise_ids`. `SeasonLine`: `year, franchise_ids, starts, points, vor, bench_points, playoff_starts, playoff_points, title`. `Stint`: `player_id, franchise_id, start, end` with `(year, week)` keys. `Move`: `kind, year, week, franchise_id, detail` where kind is one of `drafted, traded, claimed, signed, joined, traded away, dropped, left`.
- `histories: dict[str, FranchiseHistory]`; fields `id, name, eras: (EraSummary,...)` newest first, `totals: Totals`, `streak, longest_win_streak, longest_loss_streak, best_season, worst_season, series: (Series,...), top_starters: (TopStarter,...), playoff_games: (Meeting,...)`. `EraSummary`: `era, rows: (SeasonRow,...)` newest first, `totals`. `SeasonRow`: `year, name, wins, losses, ties, division_record, points_for, points_against, seed, playoff_wins, playoff_losses, finish, title, in_progress, top_starter` (a `(player_id, name, points, vor)` tuple or None). `Totals`: `games, wins, losses, ties, points_for, points_against, playoff_apps, playoff_wins, playoff_losses, titles`, plus `win_pct` and `record` properties. `Series`: `opponent_id, opponent_name, wins, losses, ties, regular, playoff, points_for, points_against, avg_margin, streak, last, meetings`. `Meeting`: `year, week, playoff, round_name, own_name, opponent_id, opponent_name, own_score, opponent_score, result`. `TopStarter`: `player_id, name, position, first_year, last_year, starts, points, vor`.
- `records: list[RecordTable]`; `RecordTable`: `key, title, group, entries, lowest_first, unit`. `RecordEntry`: `value, holder, detail, year, week, playoff, franchise_id, player_id`.
- `hall: Hall` with `players: (PlayerPlaque,...)`, `franchises: (FranchisePlaque,...)`, `watch_list: (WatchEntry,...)`, `rules`. `PlayerPlaque`: `player_id, name, position, class_year, franchise_names, starts, points, vor, titles`. `FranchisePlaque`: `franchise_id, name, class_year, titles, record, win_pct`. `WatchEntry`: `player_id, name, position, starts, vor, needed_vor, needed_starts`.
- `drafts: list[DraftSummary]` oldest first; `DraftSummary`: `year, startup, rounds, picks, steal, bust`. `PickLine`: `year, round, pick, franchise_id, franchise_name, original_owner_id, player_id, player_name, position, starts_for, points_for, vor_for, career_points, career_vor`. `draft_rankings: list[DraftRanking]` with `franchise_id, name, picks, vor`.
- `trades: list[TradeLine]` newest first; `TradeLine`: `year, timestamp, effective, pending, sides, comments, verdict`. `TradeSide`: `franchise_id, name, received, vor`. `Asset`: `code, kind, label, player_id, starts, points, vor`.
- `through: (year, week) | None` and `champions: [(year, champion_id, runner_up_id), ...]` oldest first.

`Config` (from `data/config.toml`) has `site_base_url` and `managers: (Manager(franchise, name, from_year),...)`. Tests build a `Model` with `compute(four_team_league().seasons, rules)` from `tests/hof/synthetic.py`, and the real 2020 fixture with `load_season(fixtures_dir / "raw" / "2020")`.

## Decisions that refine the spec

- **The players table is its own search index.** The spec describes a JSON index for the player search; the players index page already holds every row, so the search box filters those rows in place and no JSON file is written. Same behaviour, one fewer moving part.
- **Head-to-head rows expand with `<details>`**, not JavaScript, so the game log works without scripts.
- **Top starters on a franchise page show the top 25 with a position column** instead of era and position filters. Filters can come later without changing the data.
- **Franchise ids never reach HTML.** Player URLs end in the MFL player id, which is fine; franchise URLs use the current name's slug. A test greps the whole build for the synthetic ids.
- **Every internal link is root-relative under the Pages project path** taken from `site_base_url`, so the same build works at `/bdfl-trade-notifier/` on Pages and at `/` if the site ever moves.

## Conventions

As before: repo root, virtualenv active, `pytest`, `ruff check src tests scripts hof`, one commit per task with the `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` trailer. Templates are Jinja2 with autoescaping on; never mark anything `|safe`. Keep the build deterministic: no timestamps, no unsorted dict iteration over sets.

## File structure

| Path | Responsibility |
|---|---|
| `hof/site/__init__.py` | empty |
| `hof/site/slugs.py` | `slugify`, `unique_slugs` |
| `hof/site/build.py` | `Site` (URLs, slugs, colors), Jinja environment, page renderers, `build_site()` |
| `hof/site/templates/base.html` | layout, nav, footer |
| `hof/site/templates/home.html`, `players.html`, `player.html`, `franchises.html`, `franchise.html`, `records.html`, `hall.html`, `drafts.html`, `draft.html`, `trades.html` | one per page type |
| `hof/site/static/site.css`, `site.js` | styling; table sorting and the player search |
| `hof/__main__.py` | gains `build --out DIR` |
| `.github/workflows/hof.yml` | the weekly job |
| `tests/hof/test_hof_site.py` | build tests on the synthetic league and the 2020 fixture |

---

### Task 1: Slugs, the build skeleton, and the home page

**Files:**
- Create: `hof/site/__init__.py`, `hof/site/slugs.py`, `hof/site/build.py`, `hof/site/templates/base.html`, `hof/site/templates/home.html`, `hof/site/static/site.css`, `hof/site/static/site.js`
- Modify: `hof/__main__.py`
- Test: `tests/hof/test_hof_site.py`

- [ ] **Step 1: Write the failing tests**

`tests/hof/test_hof_site.py`:

```python
import filecmp
import re
from pathlib import Path

import pytest
from synthetic import four_team_league

from hof.config import Config, HallRules
from hof.site.build import build_site
from hof.site.slugs import slugify, unique_slugs
from hof.stats.model import compute

CONFIG = Config(
    league_id="1",
    site_base_url="https://example.test/hof/",
    league_overrides={},
    hall=HallRules(player_min_vor=40, player_min_starts=3, franchise_min_titles=1, watch_list_margin=50),
    managers=(),
)


def build_synthetic(out: Path):
    model = compute(four_team_league().seasons, CONFIG.hall)
    return build_site(model, CONFIG, out), model


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    site, model = build_synthetic(out)
    return out, site, model


def read(out: Path, relative: str) -> str:
    return (out / relative / "index.html").read_text()


def test_slugify():
    assert slugify("Marcus Peters' Peter Peckers") == "marcus-peters-peter-peckers"
    assert slugify("  Free Hernandez  Bad Boyz ") == "free-hernandez-bad-boyz"
    assert slugify("Ezekiel 23:20") == "ezekiel-23-20"
    assert slugify("Björk & Co.") == "bjork-co"
    assert slugify("!!!") == "franchise"


def test_unique_slugs_disambiguate_collisions():
    assert unique_slugs({"a": "Alpha", "b": "alpha!", "c": "Beta"}) == {"a": "alpha", "b": "alpha-2", "c": "beta"}


def test_site_urls(built):
    _, site, _ = built
    assert site.base_path == "/hof/"
    assert site.url("home") == "/hof/"
    assert site.url("player", "a1") == "/hof/players/qb-a1-a1/"
    assert site.url("franchise", "0001") == "/hof/franchises/alpha-prime/"
    assert site.url("hall") == "/hof/hall-of-fame/"
    assert site.url("draft", 2020) == "/hof/drafts/2020/"
    assert site.url("static", "site.css") == "/hof/static/site.css"


def test_home_page_and_static_assets(built):
    out, _, _ = built
    html = read(out, "")
    assert "<title>Home · BDFL Hall of Records</title>" in html
    assert 'href="/hof/static/site.css"' in html
    assert "Class of 2020" in html and "QB A1" in html
    assert "2020" in html and ">Alpha<" in html and ">Gamma<" in html  # champion and runner-up by their 2020 names
    assert "through 2021 Week 1" in html
    assert (out / "static" / "site.css").exists() and (out / "static" / "site.js").exists()


def assert_same_tree(comparison: filecmp.dircmp) -> None:
    assert not comparison.diff_files and not comparison.left_only and not comparison.right_only, comparison.report()
    for sub in comparison.subdirs.values():
        assert_same_tree(sub)


def test_build_is_deterministic(tmp_path):
    build_synthetic(tmp_path / "one")
    build_synthetic(tmp_path / "two")
    assert_same_tree(filecmp.dircmp(tmp_path / "one", tmp_path / "two"))


def test_build_replaces_a_previous_build(tmp_path):
    out = tmp_path / "site"
    out.mkdir()
    (out / "stale.html").write_text("old")
    build_synthetic(out)
    assert not (out / "stale.html").exists()


def all_html(out: Path) -> dict[str, str]:
    return {str(path.relative_to(out)): path.read_text() for path in out.rglob("*.html")}


def test_no_franchise_id_reaches_the_html(built):
    out, _, _ = built
    leak = re.compile(r"(?<![\d-])000[1-4](?!\d)")
    for name, html in all_html(out).items():
        assert not leak.search(html), f"franchise id in {name}"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_site.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'hof.site'`.

- [ ] **Step 3: Implement slugs**

`hof/site/__init__.py`: empty.

`hof/site/slugs.py`:

```python
"""URL slugs: lowercase ASCII words joined by hyphens."""

from __future__ import annotations

import re
import unicodedata

_NON_WORD = re.compile(r"[^a-z0-9]+")


def slugify(text: str, fallback: str = "franchise") -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = _NON_WORD.sub("-", ascii_text.lower()).strip("-")
    return slug or fallback


def unique_slugs(names: dict[str, str]) -> dict[str, str]:
    """Key -> slug, appending -2, -3, ... when two names slug the same; keys are processed in order."""
    taken: dict[str, int] = {}
    out: dict[str, str] = {}
    for key, name in names.items():
        base = slugify(name)
        count = taken.get(base, 0) + 1
        taken[base] = count
        out[key] = base if count == 1 else f"{base}-{count}"
    return out
```

- [ ] **Step 4: Implement the build skeleton**

`hof/site/build.py`:

```python
"""Render the computed Model into a static site."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, select_autoescape

from hof.config import Config
from hof.site.slugs import slugify, unique_slugs
from hof.stats.model import Model

PACKAGE_DIR = Path(__file__).parent
TEMPLATES = PACKAGE_DIR / "templates"
STATIC = PACKAGE_DIR / "static"
PALETTE = (
    "#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd", "#8c564b",
    "#e377c2", "#17becf", "#bcbd22", "#7f7f7f", "#393b79", "#ad494a",
)
SECTIONS = {
    "home": "",
    "players": "players/",
    "franchises": "franchises/",
    "records": "records/",
    "hall": "hall-of-fame/",
    "drafts": "drafts/",
    "trades": "trades/",
}

Page = tuple[str, str]  # (relative directory, html)
Renderer = Callable[[Environment, Model, "Site"], list[Page]]


@dataclass(frozen=True)
class Site:
    """Everything templates need to link between pages."""

    base_path: str  # starts and ends with "/"
    franchise_slugs: dict[str, str]
    player_slugs: dict[str, str]
    colors: dict[str, str]  # franchise id -> hex color for tenure bars

    def url(self, kind: str, key: str | int = "") -> str:
        if kind == "player":
            return f"{self.base_path}players/{self.player_slugs[str(key)]}/"
        if kind == "franchise":
            return f"{self.base_path}franchises/{self.franchise_slugs[str(key)]}/"
        if kind == "draft":
            return f"{self.base_path}drafts/{key}/"
        if kind == "static":
            return f"{self.base_path}static/{key}"
        return f"{self.base_path}{SECTIONS[kind]}"


def make_site(model: Model, config: Config) -> Site:
    base_path = urlsplit(config.site_base_url).path or "/"
    if not base_path.startswith("/"):
        base_path = "/" + base_path
    if not base_path.endswith("/"):
        base_path += "/"
    ids = model.league.franchise_ids()
    return Site(
        base_path=base_path,
        franchise_slugs=unique_slugs({fid: model.league.current_name(fid) for fid in ids}),
        player_slugs={pid: f"{slugify(career.name, 'player')}-{pid}" for pid, career in sorted(model.careers.items())},
        colors={fid: PALETTE[i % len(PALETTE)] for i, fid in enumerate(ids)},
    )


def through_label(model: Model) -> str:
    if model.through is None:
        return "no games played yet"
    year, week = model.through
    return f"through {year} Week {week}"


def environment(model: Model, config: Config, site: Site) -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["pts"] = lambda value: f"{value:.1f}"
    env.filters["signed"] = lambda value: f"{value:+.1f}"
    env.filters["pct"] = lambda value: "1.000" if value >= 1 else f"{value:.3f}"[1:]
    env.filters["date"] = lambda ts: datetime.fromtimestamp(ts, UTC).date().isoformat()
    env.globals.update(
        site=site,
        model=model,
        config=config,
        through=through_label(model),
        league_name=model.league.latest.name or "BDFL",
        name_in=model.league.name_in,
        current_name=model.league.current_name,
    )
    return env


def render_home(env: Environment, model: Model, site: Site) -> list[Page]:
    class_year = max((p.class_year for p in model.hall.players), default=None)
    context = {
        "class_year": class_year,
        "new_class": [p for p in model.hall.players if p.class_year == class_year],
        "champions": list(reversed(model.champions)),
        "leaders": sorted(model.careers.values(), key=lambda c: (-c.vor, c.name))[:5],
        "first_year": model.league.seasons[0].year,
    }
    return [("", env.get_template("home.html").render(**context))]


RENDERERS: list[Renderer] = [render_home]


def write_page(out: Path, relative: str, html: str) -> None:
    target = (out / relative if relative else out) / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html)


def build_site(model: Model, config: Config, out: Path) -> Site:
    """Render every page and copy the static assets into `out`, replacing whatever was there."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(STATIC, out / "static")
    site = make_site(model, config)
    env = environment(model, config, site)
    for renderer in RENDERERS:
        for relative, html in renderer(env, model, site):
            write_page(out, relative, html)
    return site
```

- [ ] **Step 5: Write the layout, the home page, and the assets**

`hof/site/templates/base.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{% block title %}{% endblock %} · BDFL Hall of Records</title>
<link rel="stylesheet" href="{{ site.url('static', 'site.css') }}">
</head>
<body>
<header class="top">
  <a class="brand" href="{{ site.url('home') }}">BDFL Hall of Records</a>
  <nav>
    <a href="{{ site.url('players') }}">Players</a>
    <a href="{{ site.url('franchises') }}">Franchises</a>
    <a href="{{ site.url('records') }}">Records</a>
    <a href="{{ site.url('hall') }}">Hall of Fame</a>
    <a href="{{ site.url('drafts') }}">Drafts</a>
    <a href="{{ site.url('trades') }}">Trades</a>
  </nav>
</header>
<main>
{% block content %}{% endblock %}
</main>
<footer>
  <p>{{ league_name }} · {{ through }}.</p>
  <p>VOR: points above the last guaranteed starter at the position that week. Data from MyFantasyLeague.</p>
</footer>
<script src="{{ site.url('static', 'site.js') }}"></script>
</body>
</html>
```

`hof/site/templates/home.html`:

```html
{% extends "base.html" %}
{% block title %}Home{% endblock %}
{% block content %}
<h1>{{ league_name }}</h1>
<p class="lede">Every start, every trade, every title since {{ first_year }}.</p>

<section>
  <h2>Hall of Fame{% if class_year %} · Class of {{ class_year }}{% endif %}</h2>
  {% if new_class %}
  <div class="plaques">
    {% for p in new_class %}
    <a class="plaque" href="{{ site.url('player', p.player_id) }}">
      <b>{{ p.name }}</b> <span class="pos">{{ p.position }}</span><br>
      {{ p.points|pts }} pts · {{ p.vor|pts }} VOR · {{ p.titles }} title{{ 's' if p.titles != 1 }}
    </a>
    {% endfor %}
  </div>
  {% else %}
  <p>No inductees yet.</p>
  {% endif %}
  <p><a href="{{ site.url('hall') }}">All inductees and the watch list</a></p>
</section>

<section>
  <h2>Champions</h2>
  <div class="table-wrap">
  <table>
    <thead><tr><th>Year</th><th>Champion</th><th>Runner-up</th></tr></thead>
    <tbody>
    {% for year, champion, runner_up in champions %}
    <tr>
      <td>{{ year }}</td>
      <td><a href="{{ site.url('franchise', champion) }}">{{ name_in(champion, year) }}</a></td>
      <td><a href="{{ site.url('franchise', runner_up) }}">{{ name_in(runner_up, year) }}</a></td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
</section>

<section>
  <h2>Career leaders</h2>
  <ol class="leaders">
    {% for c in leaders %}
    <li><a href="{{ site.url('player', c.player_id) }}">{{ c.name }}</a> <span class="pos">{{ c.position }}</span> · {{ c.vor|pts }} VOR · {{ c.points|pts }} pts · {{ c.starts }} starts</li>
    {% endfor %}
  </ol>
  <p><a href="{{ site.url('players') }}">Every player</a> · <a href="{{ site.url('records') }}">Records book</a></p>
</section>
{% endblock %}
```

`hof/site/static/site.css`:

```css
:root { --ink: #222; --muted: #666; --line: #e3e3e3; --bg: #fff; --panel: #f5f7fa; --link: #1a56b5; --gold: #b08d2b; }
* { box-sizing: border-box; }
body { margin: 0; font: 15px/1.45 -apple-system, "Segoe UI", system-ui, sans-serif; color: var(--ink); background: var(--bg); }
a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }
header.top { display: flex; flex-wrap: wrap; gap: 6px 18px; align-items: baseline; padding: 12px 20px; border-bottom: 2px solid var(--ink); }
header.top .brand { font-weight: 700; font-size: 18px; color: var(--ink); }
header.top nav a { margin-right: 14px; }
main { max-width: 980px; margin: 0 auto; padding: 18px 20px 40px; }
footer { max-width: 980px; margin: 0 auto; padding: 18px 20px 40px; color: var(--muted); font-size: 13px; border-top: 1px solid var(--line); }
h1 { font-size: 28px; margin: 6px 0 2px; }
h2 { font-size: 17px; margin: 26px 0 8px; border-bottom: 2px solid var(--ink); padding-bottom: 3px; }
h3 { font-size: 15px; margin: 16px 0 6px; }
h3 small, .muted { color: var(--muted); font-weight: 400; }
.lede { color: var(--muted); margin-top: 0; }
.pos { display: inline-block; font-size: 11px; color: var(--muted); border: 1px solid var(--line); border-radius: 3px; padding: 0 4px; vertical-align: middle; }
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { padding: 4px 7px; border-bottom: 1px solid var(--line); text-align: right; white-space: nowrap; }
th { background: #f0f0f0; color: #444; font-weight: 600; font-size: 12px; }
td:first-child, th:first-child, td.l, th.l { text-align: left; }
tr.sub td { background: #fafafa; font-weight: 600; }
table.sortable th { cursor: pointer; user-select: none; }
table.sortable th.asc::after { content: " \25B4"; }
table.sortable th.desc::after { content: " \25BE"; }
.stats { display: flex; flex-wrap: wrap; gap: 10px 26px; margin: 10px 0 8px; padding: 10px 14px; background: var(--panel); border-radius: 6px; }
.stats div { text-align: center; }
.stats b { display: block; font-size: 20px; }
.stats span { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }
.era { border-left: 4px solid #5b8def; padding-left: 12px; margin: 10px 0 18px; }
.era.old { border-left-color: #c9c9c9; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
@media (max-width: 720px) { .two { grid-template-columns: 1fr; } }
.plaques { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 10px; }
.plaque { display: block; border: 2px solid var(--gold); background: #fff8e1; border-radius: 6px; padding: 8px 10px; color: var(--ink); }
.plaque b { color: #7a5c00; }
.leaders li { margin: 3px 0; }
.tenure { display: flex; height: 14px; border-radius: 3px; overflow: hidden; margin: 6px 0 10px; }
.tenure span { display: block; height: 100%; }
.legend span { display: inline-block; margin-right: 12px; font-size: 12px; }
.legend i { display: inline-block; width: 10px; height: 10px; margin-right: 4px; border-radius: 2px; vertical-align: middle; }
.h2h details { border-bottom: 1px solid var(--line); }
.h2h summary { display: grid; grid-template-columns: 2fr repeat(6, 1fr) 2fr; gap: 6px; padding: 5px 7px; cursor: pointer; font-size: 13px; }
.h2h summary span { text-align: right; }
.h2h summary span:first-child, .h2h summary span:last-child { text-align: left; }
.h2h .head { display: grid; grid-template-columns: 2fr repeat(6, 1fr) 2fr; gap: 6px; padding: 4px 7px; background: #f0f0f0; font-size: 12px; font-weight: 600; color: #444; }
.h2h .head span { text-align: right; }
.h2h .head span:first-child, .h2h .head span:last-child { text-align: left; }
.h2h details table { margin: 4px 0 8px 12px; width: auto; }
.trade { border: 1px solid var(--line); border-radius: 6px; padding: 8px 12px; margin: 10px 0; }
.trade .verdict { color: var(--muted); font-size: 13px; }
.trade ul { margin: 4px 0 6px 18px; padding: 0; }
.callout { background: #fff8e1; border: 1px solid #e8d89a; border-radius: 4px; padding: 6px 10px; font-size: 13px; margin: 8px 0; }
.search { width: 100%; max-width: 360px; padding: 6px 8px; font-size: 14px; margin: 6px 0 10px; }
.timeline li { margin: 3px 0; }
.badge { display: inline-block; background: #1f7a3e; color: #fff; font-size: 11px; padding: 1px 6px; border-radius: 3px; vertical-align: middle; }
```

`hof/site/static/site.js`:

```js
// Table sorting on any table.sortable, and the player search on the players page. No dependencies.
(function () {
  function cellValue(row, index) {
    var cell = row.children[index];
    if (!cell) return "";
    var raw = cell.getAttribute("data-sort") || cell.textContent.trim();
    var number = parseFloat(raw.replace(/[,+]/g, ""));
    return isNaN(number) ? raw.toLowerCase() : number;
  }

  function sortTable(table, index, descending) {
    var body = table.tBodies[0];
    var rows = Array.prototype.slice.call(body.querySelectorAll("tr:not(.sub)"));
    rows.sort(function (a, b) {
      var x = cellValue(a, index), y = cellValue(b, index);
      if (typeof x === "number" && typeof y === "number") return descending ? y - x : x - y;
      x = String(x); y = String(y);
      return descending ? y.localeCompare(x) : x.localeCompare(y);
    });
    rows.forEach(function (row) { body.appendChild(row); });
    Array.prototype.forEach.call(table.tHead.rows[0].cells, function (cell) { cell.classList.remove("asc", "desc"); });
    table.tHead.rows[0].cells[index].classList.add(descending ? "desc" : "asc");
  }

  document.querySelectorAll("table.sortable").forEach(function (table) {
    if (!table.tHead || !table.tBodies.length) return;
    Array.prototype.forEach.call(table.tHead.rows[0].cells, function (cell, index) {
      cell.addEventListener("click", function () {
        var descending = !cell.classList.contains("desc");
        sortTable(table, index, descending);
      });
    });
  });

  var search = document.getElementById("player-search");
  if (search) {
    var rows = document.querySelectorAll("#players tbody tr");
    search.addEventListener("input", function () {
      var needle = search.value.trim().toLowerCase();
      rows.forEach(function (row) {
        row.hidden = needle !== "" && row.getAttribute("data-name").indexOf(needle) === -1;
      });
    });
  }
})();
```

- [ ] **Step 6: Add the `build` command**

In `hof/__main__.py`, add the imports:

```python
from hof.site.build import build_site
```

add a subparser next to `stats`:

```python
    build_parser = commands.add_parser("build", help="render the site into a directory")
    build_parser.add_argument("--out", type=Path, default=Path("dist"), help="output directory (default: dist)")
```

and handle it before `return 2`:

```python
    if args.command == "build":
        model = compute(load_all(args.data), config.hall)
        build_site(model, config, args.out)
        pages = sum(1 for _ in args.out.rglob("index.html"))
        print(f"built {pages} pages into {args.out}")
        return 0
```

Update the module docstring to `{fetch,stats,build}`. Add `dist/` to `.gitignore`.

- [ ] **Step 7: Run the tests**

Run: `pytest tests/hof/test_hof_site.py -v`
Expected: 8 passed.

- [ ] **Step 8: Lint and commit**

Run: `ruff check hof tests/hof`
Expected: no issues.

```bash
git add hof/site hof/__main__.py .gitignore tests/hof/test_hof_site.py
git commit -m "feat(hof): site build skeleton with the home page

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Players index and player pages

**Files:**
- Create: `hof/site/templates/players.html`, `hof/site/templates/player.html`
- Modify: `hof/site/build.py`
- Test: `tests/hof/test_hof_site.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/hof/test_hof_site.py`:

```python
def test_players_index_lists_every_career_sorted_by_value(built):
    out, _, _ = built
    html = read(out, "players")
    assert 'id="player-search"' in html
    assert re.findall(r'data-name="([^"]+)"', html) == ["qb a1", "qb a3", "qb a2", "qb a4"]
    assert 'href="/hof/players/qb-a1-a1/"' in html
    assert "Alpha Prime" in html  # franchises are listed by current name


def test_player_page_tells_the_whole_story(built):
    out, _, _ = built
    html = read(out, "players/qb-a1-a1")
    assert "<h1>QB A1" in html
    assert "Hall of Fame · Class of 2020" in html
    assert ">Alpha<" in html and ">Alpha Prime<" in html  # season rows use the name at the time
    assert "Joined Alpha" in html
    assert "🏆" in html
    assert "97.0" in html and "53.0" in html and "Career" in html
    assert 'class="tenure"' in html and "width:100.00%" in html
    assert "Active" in html
    inactive = read(out, "players/qb-a3-a3")
    assert "Active" not in inactive and "Left Gamma" in inactive
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_site.py -k players -v`
Expected: 2 failures with `FileNotFoundError` on `players/index.html`.

- [ ] **Step 3: Add the renderer**

In `hof/site/build.py`, add the import `from hof.stats import careers as careers_mod` and `from hof.stats.careers import Career`, then add above `RENDERERS`:

```python
def week_index(model: Model) -> dict[tuple[int, int], int]:
    """Every rostered (year, week) -> its position in the league's timeline."""
    rosters = careers_mod.rosters_by_year(model.league)
    keys = [(year, week) for year in sorted(rosters) for week in sorted(rosters[year])]
    return {key: i for i, key in enumerate(keys)}


def tenure_segments(career: Career, index: dict[tuple[int, int], int], model: Model, site: Site) -> list[dict]:
    """Bar segments across the player's career span: colored per franchise, uncolored for gaps."""
    if not career.stints:
        return []
    first = index[career.stints[0].start]
    last = max(index[s.end] for s in career.stints)
    total = last - first + 1
    segments: list[dict] = []
    cursor = first
    for stint in career.stints:
        start, end = index[stint.start], index[stint.end]
        if start > cursor:
            segments.append({"color": None, "width": f"{(start - cursor) / total * 100:.2f}", "label": ""})
        start = max(start, cursor)
        if end >= start:
            name = model.league.current_name(stint.franchise_id)
            years = f"{stint.start[0]}" if stint.start[0] == stint.end[0] else f"{stint.start[0]}–{stint.end[0]}"
            segments.append({"color": site.colors[stint.franchise_id], "width": f"{(end - start + 1) / total * 100:.2f}", "label": f"{name} {years}"})
            cursor = end + 1
    return segments


def render_players(env: Environment, model: Model, site: Site) -> list[Page]:
    careers = sorted(model.careers.values(), key=lambda c: (-c.vor, -c.points, c.name))
    pages = [("players", env.get_template("players.html").render(careers=careers))]
    index = week_index(model)
    plaques = {p.player_id: p for p in model.hall.players}
    template = env.get_template("player.html")
    for career in careers:
        pages.append(
            (
                f"players/{site.player_slugs[career.player_id]}",
                template.render(
                    career=career,
                    info=model.league.player_info(career.player_id),
                    plaque=plaques.get(career.player_id),
                    tenure=tenure_segments(career, index, model, site),
                    legend=[(fid, model.league.current_name(fid), site.colors[fid]) for fid in career.franchise_ids],
                ),
            )
        )
    return pages
```

and change `RENDERERS` to `[render_home, render_players]`.

- [ ] **Step 4: Write the templates**

`hof/site/templates/players.html`:

```html
{% extends "base.html" %}
{% block title %}Players{% endblock %}
{% block content %}
<h1>Players</h1>
<p class="lede">Everyone who ever started a game, ranked by career value over replacement. Click a column to sort.</p>
<input id="player-search" class="search" type="search" placeholder="Search players" aria-label="Search players">
<div class="table-wrap">
<table id="players" class="sortable">
  <thead><tr><th class="l">Player</th><th>Pos</th><th>Years</th><th class="l">Franchises</th><th>GS</th><th>Pts</th><th>VOR</th><th>Titles</th><th>Active</th></tr></thead>
  <tbody>
  {% for c in careers %}
  <tr data-name="{{ c.name|lower }}">
    <td class="l"><a href="{{ site.url('player', c.player_id) }}">{{ c.name }}</a></td>
    <td>{{ c.position }}</td>
    <td>{% if c.first_year == c.last_year %}{{ c.first_year }}{% else %}{{ c.first_year }}–{{ c.last_year }}{% endif %}</td>
    <td class="l">{% for fid in c.franchise_ids %}<a href="{{ site.url('franchise', fid) }}">{{ current_name(fid) }}</a>{{ ", " if not loop.last }}{% endfor %}</td>
    <td>{{ c.starts }}</td>
    <td>{{ c.points|pts }}</td>
    <td>{{ c.vor|pts }}</td>
    <td>{{ c.titles }}</td>
    <td>{{ "Yes" if c.active else "" }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
</div>
{% endblock %}
```

`hof/site/templates/player.html`:

```html
{% extends "base.html" %}
{% block title %}{{ career.name }}{% endblock %}
{% block content %}
<h1>{{ career.name }} <span class="pos">{{ career.position }}</span>{% if info.team %} <span class="muted">{{ info.team }}</span>{% endif %}{% if career.active %} <span class="badge">Active</span>{% endif %}</h1>
<p class="lede">
  {% if career.first_year == career.last_year %}{{ career.first_year }}{% else %}{{ career.first_year }}–{{ career.last_year }}{% endif %}
  · {{ career.franchise_ids|length }} franchise{{ 's' if career.franchise_ids|length != 1 }}
  · {{ career.titles }} title{{ 's' if career.titles != 1 }} as a starter
  {% if plaque %} · <a href="{{ site.url('hall') }}">Hall of Fame · Class of {{ plaque.class_year }}</a>{% endif %}
</p>

{% if tenure %}
<div class="tenure">
  {% for seg in tenure %}<span style="width:{{ seg.width }}%;{% if seg.color %}background:{{ seg.color }}{% endif %}" title="{{ seg.label }}"></span>{% endfor %}
</div>
<p class="legend">{% for fid, name, color in legend %}<span><i style="background:{{ color }}"></i><a href="{{ site.url('franchise', fid) }}">{{ name }}</a></span>{% endfor %}</p>
{% endif %}

<h2>Season by season</h2>
<div class="table-wrap">
<table>
  <thead><tr><th>Year</th><th class="l">Franchise</th><th>GS</th><th>Pts</th><th>VOR</th><th>Bench</th><th>PO GS</th><th>PO Pts</th><th>Title</th></tr></thead>
  <tbody>
  {% for line in career.seasons %}
  <tr>
    <td>{{ line.year }}</td>
    <td class="l">{% for fid in line.franchise_ids %}<a href="{{ site.url('franchise', fid) }}">{{ name_in(fid, line.year) }}</a>{{ ", " if not loop.last }}{% endfor %}</td>
    <td>{{ line.starts }}</td>
    <td>{{ line.points|pts }}</td>
    <td>{{ line.vor|pts }}</td>
    <td>{{ line.bench_points|pts }}</td>
    <td>{{ line.playoff_starts }}</td>
    <td>{{ line.playoff_points|pts }}</td>
    <td>{{ "🏆" if line.title }}</td>
  </tr>
  {% endfor %}
  <tr class="sub">
    <td>Career</td><td class="l"></td>
    <td>{{ career.starts }}</td><td>{{ career.points|pts }}</td><td>{{ career.vor|pts }}</td><td>{{ career.bench_points|pts }}</td>
    <td>{{ career.playoff_starts }}</td><td>{{ career.playoff_points|pts }}</td><td>{{ career.titles or "" }}</td>
  </tr>
  </tbody>
</table>
</div>

<h2>Transactions</h2>
<ol class="timeline">
{% for move in career.moves %}
  {% set team = name_in(move.franchise_id, move.year) %}
  <li>{{ move.year }} Week {{ move.week }}:
    {% if move.kind == "drafted" %}Drafted by {{ team }} ({{ move.detail }})
    {% elif move.kind == "traded" %}Traded to {{ team }} {{ move.detail }}
    {% elif move.kind == "claimed" %}Claimed on waivers by {{ team }} for {{ move.detail }}
    {% elif move.kind == "signed" %}Signed by {{ team }}
    {% elif move.kind == "joined" %}Joined {{ team }}
    {% elif move.kind == "traded away" %}Traded away by {{ team }} {{ move.detail }}
    {% elif move.kind == "dropped" %}Dropped by {{ team }}
    {% else %}Left {{ team }}
    {% endif %}
  </li>
{% endfor %}
</ol>
{% endblock %}
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/hof/test_hof_site.py -v`
Expected: 10 passed. If the tenure assertion fails, print the bar: QB A1 has one stint spanning the whole career, so its single segment must be exactly `width:100.00%`.

- [ ] **Step 6: Lint and commit**

Run: `ruff check hof tests/hof`
Expected: no issues.

```bash
git add hof/site tests/hof/test_hof_site.py
git commit -m "feat(hof): players index and player pages

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Franchises index and franchise pages

**Files:**
- Create: `hof/site/templates/franchises.html`, `hof/site/templates/franchise.html`
- Modify: `hof/site/build.py`, `hof/site/static/site.css`
- Test: `tests/hof/test_hof_site.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/hof/test_hof_site.py`:

```python
def test_franchises_index_ranks_by_win_percentage(built):
    out, _, _ = built
    html = read(out, "franchises")
    names = re.findall(r'href="/hof/franchises/[^"]+/">([^<]+)</a>', html)
    assert names == ["Gamma", "Alpha Prime", "Delta", "Beta"]
    assert "1.000" in html and ".667" in html


def test_franchise_page_groups_seasons_by_era(built):
    out, _, _ = built
    html = read(out, "franchises/alpha-prime")
    assert "<h1>Alpha Prime" in html
    assert "Formerly" in html and "<b>Alpha</b> (2020)" in html
    assert "As Alpha Prime" in html and "As Alpha <small>" in html
    assert html.index("As Alpha Prime") < html.index("As Alpha <small>")  # newest era first
    assert "Champion" in html and "In progress" in html
    assert "<b>2-1-0</b>" in html  # all-time record in the summary row
    assert "Head-to-head" in html and "<summary>" in html and ">Beta<" in html and "2-0-0" in html
    assert "Final" in html and "Semifinal" in html  # playoff history
    assert 'href="/hof/players/qb-a1-a1/">QB A1</a>' in html
    assert "No draft picks" in html and "No trades" in html
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_site.py -k franchise -v`
Expected: 2 failures with `FileNotFoundError` on `franchises/index.html`.

- [ ] **Step 3: Add the renderer**

In `hof/site/build.py`, add above `RENDERERS`:

```python
def render_franchises(env: Environment, model: Model, site: Site) -> list[Page]:
    histories = sorted(model.histories.values(), key=lambda h: (-h.totals.win_pct, -h.totals.points_for, h.name))
    pages = [("franchises", env.get_template("franchises.html").render(histories=histories))]
    template = env.get_template("franchise.html")
    managers = env.globals["config"].managers
    for history in histories:
        eras = model.league.eras(history.id)
        pages.append(
            (
                f"franchises/{site.franchise_slugs[history.id]}",
                template.render(
                    h=history,
                    former=[era for era in eras if era.name != history.name],
                    managers=sorted((m for m in managers if m.franchise == history.id), key=lambda m: -m.from_year),
                    picks=[line for summary in reversed(model.drafts) for line in summary.picks if line.franchise_id == history.id],
                    trades=[t for t in model.trades if any(side.franchise_id == history.id for side in t.sides)],
                    top=history.top_starters[:25],
                ),
            )
        )
    return pages
```

and change `RENDERERS` to `[render_home, render_players, render_franchises]`.

- [ ] **Step 4: Write the templates**

`hof/site/templates/franchises.html`:

```html
{% extends "base.html" %}
{% block title %}Franchises{% endblock %}
{% block content %}
<h1>Franchises</h1>
<p class="lede">All-time standings, regular season only. Click a column to sort.</p>
<div class="table-wrap">
<table class="sortable">
  <thead><tr><th class="l">Franchise</th><th>Record</th><th>Pct</th><th>PF</th><th>PA</th><th>Playoffs</th><th>PO record</th><th>Titles</th><th>Streak</th></tr></thead>
  <tbody>
  {% for h in histories %}
  <tr>
    <td class="l"><a href="{{ site.url('franchise', h.id) }}">{{ h.name }}</a></td>
    <td>{{ h.totals.record }}</td>
    <td>{{ h.totals.win_pct|pct }}</td>
    <td>{{ h.totals.points_for|pts }}</td>
    <td>{{ h.totals.points_against|pts }}</td>
    <td>{{ h.totals.playoff_apps }}</td>
    <td>{{ h.totals.playoff_wins }}-{{ h.totals.playoff_losses }}</td>
    <td>{{ h.totals.titles }}</td>
    <td>{{ h.streak }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
</div>
{% endblock %}
```

`hof/site/templates/franchise.html`:

```html
{% extends "base.html" %}
{% block title %}{{ h.name }}{% endblock %}
{% block content %}
{% macro years(first, last) %}{% if first == last %}{{ first }}{% else %}{{ first }}–{{ last }}{% endif %}{% endmacro %}
<h1>{{ h.name }}</h1>
<p class="lede">
  {% if former %}Formerly {% for e in former %}<b>{{ e.name }}</b> ({{ years(e.first_year, e.last_year) }}){{ ", " if not loop.last }}{% endfor %}{% endif %}
  {% if managers %}{% if former %} · {% endif %}Manager: {{ managers[0].name }}{% if managers|length > 1 %} (previously {% for m in managers[1:] %}{{ m.name }}{{ ", " if not loop.last }}{% endfor %}){% endif %}{% endif %}
</p>

<div class="stats">
  <div><b>{{ h.totals.record }}</b><span>All-time</span></div>
  <div><b>{{ h.totals.titles }}</b><span>Titles</span></div>
  <div><b>{{ h.totals.playoff_apps }}</b><span>Playoff apps</span></div>
  <div><b>{{ h.totals.playoff_wins }}-{{ h.totals.playoff_losses }}</b><span>Playoff rec</span></div>
  <div><b>{{ h.totals.points_for|pts }}</b><span>Points for</span></div>
  <div><b>{{ h.totals.points_against|pts }}</b><span>Points against</span></div>
  <div><b>{{ h.streak or "—" }}</b><span>Streak</span></div>
</div>

<h2>Season by season</h2>
{% for summary in h.eras %}
<div class="era{% if not loop.first %} old{% endif %}">
  <h3>As {{ summary.era.name }} <small>{{ years(summary.era.first_year, summary.era.last_year) }} · {{ summary.totals.record }} · {{ summary.totals.titles }} title{{ 's' if summary.totals.titles != 1 }}</small></h3>
  <div class="table-wrap">
  <table>
    <thead><tr><th>Year</th><th>W-L-T</th><th>Div</th><th>PF</th><th>PA</th><th>Seed</th><th class="l">Finish</th><th class="l">Top starter</th></tr></thead>
    <tbody>
    {% for row in summary.rows %}
    <tr>
      <td>{{ row.year }}</td>
      <td>{{ row.wins }}-{{ row.losses }}-{{ row.ties }}</td>
      <td>{{ row.division_record }}</td>
      <td>{{ row.points_for|pts }}</td>
      <td>{{ row.points_against|pts }}</td>
      <td>{{ row.seed or "–" }}</td>
      <td class="l">{% if row.title %}🏆 {% endif %}{{ row.finish }}</td>
      <td class="l">{% if row.top_starter %}<a href="{{ site.url('player', row.top_starter[0]) }}">{{ row.top_starter[1] }}</a> {{ row.top_starter[2]|pts }}{% endif %}</td>
    </tr>
    {% endfor %}
    <tr class="sub">
      <td>Era</td><td>{{ summary.totals.record }}</td><td></td>
      <td>{{ summary.totals.points_for|pts }}</td><td>{{ summary.totals.points_against|pts }}</td><td></td>
      <td class="l">{{ summary.totals.titles }} title{{ 's' if summary.totals.titles != 1 }} · {{ summary.totals.playoff_apps }} playoff app{{ 's' if summary.totals.playoff_apps != 1 }}</td><td></td>
    </tr>
    </tbody>
  </table>
  </div>
</div>
{% endfor %}

<div class="two">
  <div>
    <h2>All-time top starters</h2>
    <div class="table-wrap">
    <table class="sortable">
      <thead><tr><th>#</th><th class="l">Player</th><th>Pos</th><th>Yrs</th><th>GS</th><th>Pts</th><th>VOR</th></tr></thead>
      <tbody>
      {% for t in top %}
      <tr><td>{{ loop.index }}</td><td class="l"><a href="{{ site.url('player', t.player_id) }}">{{ t.name }}</a></td><td>{{ t.position }}</td><td>{{ years(t.first_year, t.last_year) }}</td><td>{{ t.starts }}</td><td>{{ t.points|pts }}</td><td>{{ t.vor|pts }}</td></tr>
      {% endfor %}
      </tbody>
    </table>
    </div>
  </div>
  <div>
    <h2>Playoff history</h2>
    {% if h.playoff_games %}
    <div class="table-wrap">
    <table>
      <thead><tr><th>Year</th><th class="l">Round</th><th class="l">Opponent</th><th>Score</th><th>Res</th></tr></thead>
      <tbody>
      {% for m in h.playoff_games %}
      <tr><td>{{ m.year }}</td><td class="l">{{ m.round_name }}</td><td class="l"><a href="{{ site.url('franchise', m.opponent_id) }}">{{ m.opponent_name }}</a></td><td>{{ m.own_score|pts }}–{{ m.opponent_score|pts }}</td><td>{{ m.result }}{% if m.result == "W" and m.round_name == "Final" %} 🏆{% endif %}</td></tr>
      {% endfor %}
      </tbody>
    </table>
    </div>
    {% else %}<p class="muted">No playoff games yet.</p>{% endif %}
  </div>
</div>

<h2>Head-to-head</h2>
<p class="callout">All-time series against every other franchise, by their current name. Open a row for every meeting, with the names both teams used at the time.</p>
<div class="h2h">
  <div class="head"><span>Opponent</span><span>All-time</span><span>Reg</span><span>Playoffs</span><span>PF</span><span>PA</span><span>Margin</span><span>Streak</span><span>Last meeting</span></div>
  {% for s in h.series %}
  <details>
    <summary>
      <span><a href="{{ site.url('franchise', s.opponent_id) }}">{{ s.opponent_name }}</a></span>
      <span>{{ s.wins }}-{{ s.losses }}-{{ s.ties }}</span>
      <span>{{ s.regular[0] }}-{{ s.regular[1] }}-{{ s.regular[2] }}</span>
      <span>{% if s.playoff[0] + s.playoff[1] + s.playoff[2] %}{{ s.playoff[0] }}-{{ s.playoff[1] }}{% else %}–{% endif %}</span>
      <span>{{ s.points_for|pts }}</span>
      <span>{{ s.points_against|pts }}</span>
      <span>{{ s.avg_margin|signed }}</span>
      <span>{{ s.streak }}</span>
      <span>{% if s.last %}{{ s.last.year }} {{ s.last.round_name or ("Wk " ~ s.last.week) }}, {{ s.last.result }} {{ s.last.own_score|pts }}–{{ s.last.opponent_score|pts }}{% endif %}</span>
    </summary>
    <table>
      <thead><tr><th>Year</th><th>Wk</th><th class="l">Round</th><th class="l">As</th><th class="l">Opponent</th><th>Score</th><th>Res</th></tr></thead>
      <tbody>
      {% for m in s.meetings|reverse %}
      <tr><td>{{ m.year }}</td><td>{{ m.week }}</td><td class="l">{{ m.round_name or "" }}</td><td class="l">{{ m.own_name }}</td><td class="l">{{ m.opponent_name }}</td><td>{{ m.own_score|pts }}–{{ m.opponent_score|pts }}</td><td>{{ m.result }}</td></tr>
      {% endfor %}
      </tbody>
    </table>
  </details>
  {% endfor %}
</div>

<div class="two">
  <div>
    <h2>Draft picks</h2>
    {% if picks %}
    <div class="table-wrap">
    <table>
      <thead><tr><th>Year</th><th>Pick</th><th class="l">Player</th><th>Pts</th><th>VOR</th></tr></thead>
      <tbody>
      {% for p in picks %}
      <tr><td><a href="{{ site.url('draft', p.year) }}">{{ p.year }}</a></td><td>{{ p.round }}.{{ "%02d"|format(p.pick) }}</td><td class="l">{% if p.player_id in site.player_slugs %}<a href="{{ site.url('player', p.player_id) }}">{{ p.player_name }}</a>{% else %}{{ p.player_name }}{% endif %}</td><td>{{ p.points_for|pts }}</td><td>{{ p.vor_for|pts }}</td></tr>
      {% endfor %}
      </tbody>
    </table>
    </div>
    {% else %}<p class="muted">No draft picks recorded.</p>{% endif %}
  </div>
  <div>
    <h2>Trades</h2>
    {% if trades %}
    <div class="table-wrap">
    <table>
      <thead><tr><th>Date</th><th class="l">With</th><th class="l">Got</th><th class="l">Gave</th><th class="l">Verdict</th></tr></thead>
      <tbody>
      {% for t in trades %}
      {% set own = t.sides[0] if t.sides[0].franchise_id == h.id else t.sides[1] %}
      {% set other = t.sides[1] if t.sides[0].franchise_id == h.id else t.sides[0] %}
      <tr>
        <td><a href="{{ site.url('trades') }}#t{{ t.year }}-{{ t.timestamp }}">{{ t.timestamp|date }}</a></td>
        <td class="l"><a href="{{ site.url('franchise', other.franchise_id) }}">{{ other.name }}</a></td>
        <td class="l">{% for a in own.received %}{{ a.label }}{{ "; " if not loop.last }}{% endfor %}</td>
        <td class="l">{% for a in other.received %}{{ a.label }}{{ "; " if not loop.last }}{% endfor %}</td>
        <td class="l">{{ t.verdict }}</td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
    </div>
    {% else %}<p class="muted">No trades recorded.</p>{% endif %}
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Widen the head-to-head grid**

The summary row has nine columns. In `hof/site/static/site.css`, change both `grid-template-columns: 2fr repeat(6, 1fr) 2fr;` occurrences to `grid-template-columns: 2fr repeat(7, 1fr) 2fr;`.

- [ ] **Step 6: Run the tests**

Run: `pytest tests/hof/test_hof_site.py -v`
Expected: 12 passed. The `No draft picks` / `No trades` strings come from the synthetic league having neither; the fixture test in Task 6 covers the populated tables.

- [ ] **Step 7: Lint and commit**

Run: `ruff check hof tests/hof`
Expected: no issues.

```bash
git add hof/site tests/hof/test_hof_site.py
git commit -m "feat(hof): franchises index and franchise pages with eras and head-to-head

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Records book and Hall of Fame pages

**Files:**
- Create: `hof/site/templates/records.html`, `hof/site/templates/hall.html`
- Modify: `hof/site/build.py`
- Test: `tests/hof/test_hof_site.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/hof/test_hof_site.py`:

```python
def test_records_page_has_every_table(built):
    out, _, model = built
    html = read(out, "records")
    for table in model.records:
        assert table.title in html
    assert "Team, single game" in html and "Player, career" in html
    assert 'href="/hof/players/qb-a1-a1/">QB A1</a>' in html
    assert 'href="/hof/franchises/alpha-prime/">Alpha</a>' in html  # the name at the time links to the current page
    assert "vs Gamma, 2020 Week 4 (Final)" in html
    assert "1.000" in html  # best record, formatted as a percentage


def test_hall_of_fame_page(built):
    out, _, _ = built
    html = read(out, "hall-of-fame")
    assert "Class of 2020" in html
    assert 'href="/hof/players/qb-a1-a1/"' in html and "Alpha Prime" in html
    assert "Watch list" in html and "QB A2" in html and "30.0" in html
    assert "40.0 value over replacement" in html and "3 starts" in html and "1 title" in html
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/hof/test_hof_site.py -k "records or hall" -v`
Expected: 2 failures with `FileNotFoundError`.

- [ ] **Step 3: Add the renderers**

In `hof/site/build.py`, add above `RENDERERS`:

```python
def render_records(env: Environment, model: Model, site: Site) -> list[Page]:
    groups: dict[str, list] = {}
    for table in model.records:
        groups.setdefault(table.group, []).append(table)
    return [("records", env.get_template("records.html").render(groups=groups))]


def render_hall(env: Environment, model: Model, site: Site) -> list[Page]:
    years = {p.class_year for p in model.hall.players} | {f.class_year for f in model.hall.franchises}
    context = {
        "hall": model.hall,
        "classes": [
            (
                year,
                [p for p in model.hall.players if p.class_year == year],
                [f for f in model.hall.franchises if f.class_year == year],
            )
            for year in sorted(years, reverse=True)
        ],
    }
    return [("hall-of-fame", env.get_template("hall.html").render(**context))]
```

and extend `RENDERERS` with `render_records, render_hall`. Add a filter to `environment()` for record marks:

```python
    def mark(value: float, unit: str) -> str:
        if unit in ("starts", "games", "titles"):
            return str(int(value))
        if unit == "pct":
            return "1.000" if value >= 1 else f"{value:.3f}"[1:]
        return f"{value:.1f}"

    env.filters["mark"] = mark
```

- [ ] **Step 4: Write the templates**

`hof/site/templates/records.html`:

```html
{% extends "base.html" %}
{% block title %}Records{% endblock %}
{% block content %}
<h1>Records book</h1>
<p class="lede">Top ten for every record, over counted games only. Playoff games are marked.</p>
{% for group, tables in groups.items() %}
<h2>{{ group }}</h2>
<div class="two">
{% for table in tables %}
  <div>
    <h3>{{ table.title }}</h3>
    <div class="table-wrap">
    <table>
      <thead><tr><th>#</th><th class="l">Holder</th><th>Mark</th><th class="l">Detail</th></tr></thead>
      <tbody>
      {% for e in table.entries %}
      <tr>
        <td>{{ loop.index }}</td>
        <td class="l">{% if e.player_id and e.player_id in site.player_slugs %}<a href="{{ site.url('player', e.player_id) }}">{{ e.holder }}</a>{% elif e.franchise_id %}<a href="{{ site.url('franchise', e.franchise_id) }}">{{ e.holder }}</a>{% else %}{{ e.holder }}{% endif %}</td>
        <td>{{ e.value|mark(table.unit) }}</td>
        <td class="l">{{ e.detail }}{% if e.playoff and table.group.endswith("single game") %} <span class="pos">PO</span>{% endif %}</td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
    </div>
  </div>
{% endfor %}
</div>
{% endfor %}
{% endblock %}
```

`hof/site/templates/hall.html`:

```html
{% extends "base.html" %}
{% block title %}Hall of Fame{% endblock %}
{% block content %}
<h1>Hall of Fame</h1>
<p class="lede">
  A player is inducted at the end of a season once their career value over replacement reaches {{ hall.rules.player_min_vor|pts }} value over replacement with at least {{ hall.rules.player_min_starts }} starts.
  A franchise is inducted with {{ hall.rules.franchise_min_titles }} title{{ 's' if hall.rules.franchise_min_titles != 1 }}.
</p>

{% for year, players, franchises in classes %}
<h2>Class of {{ year }}</h2>
<div class="plaques">
  {% for p in players %}
  <a class="plaque" href="{{ site.url('player', p.player_id) }}">
    <b>{{ p.name }}</b> <span class="pos">{{ p.position }}</span><br>
    <span class="muted">{{ p.franchise_names|join(", ") }}</span><br>
    {{ p.starts }} starts · {{ p.points|pts }} pts · {{ p.vor|pts }} VOR · {{ p.titles }} title{{ 's' if p.titles != 1 }} as a starter
  </a>
  {% endfor %}
  {% for f in franchises %}
  <a class="plaque" href="{{ site.url('franchise', f.franchise_id) }}">
    <b>{{ f.name }}</b> <span class="pos">Franchise</span><br>
    {{ f.titles }} title{{ 's' if f.titles != 1 }} · {{ f.record }} all-time · {{ f.win_pct|pct }}
  </a>
  {% endfor %}
</div>
{% else %}
<p>No inductees yet.</p>
{% endfor %}

<h2>Watch list</h2>
{% if hall.watch_list %}
<p class="muted">Active players within {{ hall.rules.watch_list_margin|pts }} of the line.</p>
<div class="table-wrap">
<table>
  <thead><tr><th class="l">Player</th><th>Pos</th><th>GS</th><th>VOR</th><th>Needs</th></tr></thead>
  <tbody>
  {% for w in hall.watch_list %}
  <tr>
    <td class="l"><a href="{{ site.url('player', w.player_id) }}">{{ w.name }}</a></td>
    <td>{{ w.position }}</td>
    <td>{{ w.starts }}</td>
    <td>{{ w.vor|pts }}</td>
    <td>{{ w.needed_vor|pts }}{% if w.needed_starts %} and {{ w.needed_starts }} start{{ 's' if w.needed_starts != 1 }}{% endif %}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
</div>
{% else %}
<p class="muted">Nobody is close.</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/hof/test_hof_site.py -v`
Expected: 14 passed.

- [ ] **Step 6: Lint and commit**

Run: `ruff check hof tests/hof`
Expected: no issues.

```bash
git add hof/site tests/hof/test_hof_site.py
git commit -m "feat(hof): records book and Hall of Fame pages

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Drafts and the trade ledger

**Files:**
- Create: `hof/site/templates/drafts.html`, `hof/site/templates/draft.html`, `hof/site/templates/trades.html`
- Modify: `hof/site/build.py`
- Test: `tests/hof/test_hof_site.py` (append)

The synthetic league has no drafts or trades, so these tests only pin the empty states; Task 6 checks the populated pages against the real 2020 fixture.

- [ ] **Step 1: Write the failing tests**

Append to `tests/hof/test_hof_site.py`:

```python
def test_drafts_and_trades_pages_exist_with_empty_states(built):
    out, _, _ = built
    assert "No drafts recorded" in read(out, "drafts")
    assert "No trades recorded" in read(out, "trades")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/hof/test_hof_site.py -k "drafts_and_trades" -v`
Expected: 1 failure with `FileNotFoundError`.

- [ ] **Step 3: Add the renderers**

In `hof/site/build.py`, add above `RENDERERS`:

```python
def render_drafts(env: Environment, model: Model, site: Site) -> list[Page]:
    summaries = list(reversed(model.drafts))
    pages = [("drafts", env.get_template("drafts.html").render(rankings=model.draft_rankings, summaries=summaries))]
    template = env.get_template("draft.html")
    for summary in summaries:
        pages.append((f"drafts/{summary.year}", template.render(d=summary)))
    return pages


def render_trades(env: Environment, model: Model, site: Site) -> list[Page]:
    by_year: dict[int, list] = {}
    for line in model.trades:
        by_year.setdefault(line.year, []).append(line)
    return [("trades", env.get_template("trades.html").render(by_year=by_year))]
```

and extend `RENDERERS` with `render_drafts, render_trades`, so the full list reads `[render_home, render_players, render_franchises, render_records, render_hall, render_drafts, render_trades]`.

- [ ] **Step 4: Write the templates**

`hof/site/templates/drafts.html`:

```html
{% extends "base.html" %}
{% block title %}Drafts{% endblock %}
{% block content %}
<h1>Drafts</h1>
<p class="lede">Every pick with hindsight: what it produced as a starter for the team that made it.</p>
{% if summaries %}
<h2>Who drafts best</h2>
<div class="table-wrap">
<table class="sortable">
  <thead><tr><th class="l">Franchise</th><th>Picks</th><th>VOR from picks</th></tr></thead>
  <tbody>
  {% for r in rankings %}
  <tr><td class="l"><a href="{{ site.url('franchise', r.franchise_id) }}">{{ r.name }}</a></td><td>{{ r.picks }}</td><td>{{ r.vor|pts }}</td></tr>
  {% endfor %}
  </tbody>
</table>
</div>
<h2>By year</h2>
<div class="table-wrap">
<table>
  <thead><tr><th>Year</th><th>Rounds</th><th class="l">Steal</th><th class="l">Bust</th></tr></thead>
  <tbody>
  {% for d in summaries %}
  <tr>
    <td><a href="{{ site.url('draft', d.year) }}">{{ d.year }}{% if d.startup %} (startup){% endif %}</a></td>
    <td>{{ d.rounds }}</td>
    <td class="l">{% if d.steal %}{{ d.steal.player_name }}, {{ d.steal.round }}.{{ "%02d"|format(d.steal.pick) }} by {{ d.steal.franchise_name }} ({{ d.steal.vor_for|pts }} VOR){% endif %}</td>
    <td class="l">{% if d.bust %}{{ d.bust.player_name }}, {{ d.bust.round }}.{{ "%02d"|format(d.bust.pick) }} by {{ d.bust.franchise_name }} ({{ d.bust.vor_for|pts }} VOR){% endif %}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
</div>
{% else %}
<p class="muted">No drafts recorded.</p>
{% endif %}
{% endblock %}
```

`hof/site/templates/draft.html`:

```html
{% extends "base.html" %}
{% block title %}{{ d.year }} draft{% endblock %}
{% block content %}
<h1>{{ d.year }} {{ "startup" if d.startup else "rookie" }} draft</h1>
<p class="lede">{{ d.rounds }} rounds. Points and VOR are what each player produced as a starter for the team that drafted them; career columns count every team.</p>
{% if d.steal or d.bust %}
<p class="callout">
  {% if d.steal %}<b>Steal:</b> {{ d.steal.player_name }} at {{ d.steal.round }}.{{ "%02d"|format(d.steal.pick) }} by {{ d.steal.franchise_name }}, {{ d.steal.vor_for|pts }} VOR.{% endif %}
  {% if d.bust %}<b>Bust:</b> {{ d.bust.player_name }} at {{ d.bust.round }}.{{ "%02d"|format(d.bust.pick) }} by {{ d.bust.franchise_name }}, {{ d.bust.vor_for|pts }} VOR.{% endif %}
</p>
{% endif %}
<div class="table-wrap">
<table class="sortable">
  <thead><tr><th>Pick</th><th class="l">Team</th><th class="l">Via</th><th class="l">Player</th><th>Pos</th><th>GS</th><th>Pts</th><th>VOR</th><th>Career pts</th><th>Career VOR</th></tr></thead>
  <tbody>
  {% for p in d.picks %}
  <tr>
    <td data-sort="{{ p.round * 100 + p.pick }}">{{ p.round }}.{{ "%02d"|format(p.pick) }}</td>
    <td class="l"><a href="{{ site.url('franchise', p.franchise_id) }}">{{ p.franchise_name }}</a></td>
    <td class="l">{% if p.original_owner_id and p.original_owner_id != p.franchise_id %}{{ name_in(p.original_owner_id, p.year) }}{% endif %}</td>
    <td class="l">{% if p.player_id in site.player_slugs %}<a href="{{ site.url('player', p.player_id) }}">{{ p.player_name }}</a>{% else %}{{ p.player_name }}{% endif %}</td>
    <td>{{ p.position }}</td>
    <td>{{ p.starts_for }}</td>
    <td>{{ p.points_for|pts }}</td>
    <td>{{ p.vor_for|pts }}</td>
    <td>{{ p.career_points|pts }}</td>
    <td>{{ p.career_vor|pts }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
</div>
{% endblock %}
```

`hof/site/templates/trades.html`:

```html
{% extends "base.html" %}
{% block title %}Trades{% endblock %}
{% block content %}
<h1>Trade ledger</h1>
<p class="lede">Every trade, newest first. Each side is credited with what it received produced as starters for that team from the trade onward; picks count the player they became.</p>
{% if by_year %}
<p>{% for year in by_year %}<a href="#y{{ year }}">{{ year }}</a>{{ " · " if not loop.last }}{% endfor %}</p>
{% for year, lines in by_year.items() %}
<h2 id="y{{ year }}">{{ year }}</h2>
{% for t in lines %}
<article class="trade" id="t{{ t.year }}-{{ t.timestamp }}">
  <p><b>{{ t.timestamp|date }}</b> · <a href="{{ site.url('franchise', t.sides[0].franchise_id) }}">{{ t.sides[0].name }}</a> ⇄ <a href="{{ site.url('franchise', t.sides[1].franchise_id) }}">{{ t.sides[1].name }}</a>{% if t.pending %} <span class="pos">Pending</span>{% endif %}</p>
  <div class="two">
    {% for side in t.sides %}
    <div>
      <b>{{ side.name }} received</b>
      <ul>
      {% for a in side.received %}
        <li>{{ a.label }}{% if a.player_id and not t.pending %} <span class="muted">{{ a.starts }} GS, {{ a.points|pts }} pts, {{ a.vor|pts }} VOR</span>{% endif %}</li>
      {% else %}
        <li class="muted">nothing</li>
      {% endfor %}
      </ul>
    </div>
    {% endfor %}
  </div>
  <p class="verdict">{{ t.verdict }}{% if t.comments %} · “{{ t.comments }}”{% endif %}</p>
</article>
{% endfor %}
{% endfor %}
{% else %}
<p class="muted">No trades recorded.</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/hof/test_hof_site.py -v`
Expected: 15 passed.

- [ ] **Step 6: Lint and commit**

Run: `ruff check hof tests/hof`
Expected: no issues.

```bash
git add hof/site tests/hof/test_hof_site.py
git commit -m "feat(hof): draft and trade ledger pages

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Whole-site checks and the README

**Files:**
- Modify: `README.md`, `.gitignore`
- Test: `tests/hof/test_hof_site.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/hof/test_hof_site.py`:

```python
CONFIG_PATH = Path(__file__).resolve().parents[2] / "data" / "config.toml"


def test_internal_links_resolve(built):
    out, site, _ = built
    for name, html in all_html(out).items():
        for href in re.findall(r'href="([^"]+)"', html):
            if not href.startswith(site.base_path):
                continue
            path = href[len(site.base_path):].split("#")[0]
            target = (out / path / "index.html") if (path == "" or path.endswith("/")) else out / path
            assert target.exists(), f"{name} links to {href}"


def test_real_2020_fixture_builds_a_full_site(tmp_path, fixtures_dir):
    from hof.snapshots import load_season

    config = Config.load(CONFIG_PATH)
    model = compute([load_season(fixtures_dir / "raw" / "2020")], config.hall)
    out = tmp_path / "dist"
    site = build_site(model, config, out)
    assert site.base_path == "/bdfl-trade-notifier/"
    pages = all_html(out)
    assert sum(1 for name in pages if name.startswith("franchises/") and name != "franchises/index.html") == 12
    assert sum(1 for name in pages if name.startswith("players/") and name != "players/index.html") > 100
    assert len(re.findall(r'data-sort="\d+"', pages["drafts/2020/index.html"])) == 48
    assert pages["trades/index.html"].count('class="trade"') == 20
    home = pages["index.html"]
    assert "Marcus Peters&#39; Peter Peckers" in home  # autoescaped apostrophe
    assert "through 2020 Week 16" in home
    leak = re.compile(r"(?<![\d-])00(0[1-9]|1[0-2])(?!\d)")
    for name, html in pages.items():
        assert not leak.search(html), f"franchise id in {name}"


def test_cli_build_writes_the_site(tmp_path, fixtures_dir, capsys):
    from hof import __main__ as cli

    out = tmp_path / "dist"
    code = cli.main(["--data", str(fixtures_dir), "--config", str(CONFIG_PATH), "build", "--out", str(out)])
    assert code == 0
    assert (out / "index.html").exists()
    assert "built" in capsys.readouterr().out
```

- [ ] **Step 2: Run them**

Run: `pytest tests/hof/test_hof_site.py -v`
Expected: 18 passed. These are checks on code that already exists, so they may pass first time; a failure in the fixture test is a real rendering bug (an unescaped name, a missing page, a leaked id) to fix in the template or renderer, not in the assertion. If the leak regex fires, print the surrounding 40 characters to see which template printed an id.

- [ ] **Step 3: Update the README**

Replace the "Hall of Records (in progress)" section of `README.md` with:

````markdown
## Hall of Records

`hof/` builds the league's records site from MFL history: every player's career as a BDFL starter, franchise histories, head-to-head series, a records book, a rule-based Hall of Fame, draft hindsight, and a trade ledger. Design: `docs/superpowers/specs/2026-09-06-hall-of-records-design.md`.

```bash
python -m hof fetch                 # refresh the current season; completed seasons are skipped
python -m hof stats                 # calibration report for the Hall of Fame thresholds in data/config.toml
python -m hof build --out dist      # render the site
```

Preview locally under the same path GitHub Pages uses:

```bash
python -m hof build --out preview/bdfl-trade-notifier && python -m http.server -d preview 8000
```

then open http://localhost:8000/bdfl-trade-notifier/.

### Publishing

`.github/workflows/hof.yml` runs every Tuesday at 11:00 UTC from September through January, and on any push to `main` that touches `hof/`, `data/`, or the MFL client. Each run refetches the current season from MFL, commits any changed snapshots to `main`, builds the site, and deploys it to GitHub Pages. One-time setup: in the repository settings under Pages, set the source to "GitHub Actions". The site is at `https://btcookies.github.io/bdfl-trade-notifier/`; change `site_base_url` in `data/config.toml` if it ever moves.

Hall of Fame thresholds live in `data/config.toml`. Run `python -m hof stats` to see how many players each threshold would induct before changing them.
````

Add `preview/` to `.gitignore` next to `dist/`.

- [ ] **Step 4: Full suite, lint, commit**

Run: `ruff check src tests scripts hof && pytest`
Expected: no lint issues; every test passes.

```bash
git add README.md .gitignore tests/hof/test_hof_site.py
git commit -m "test(hof): whole-site checks on the 2020 fixture; document the site

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: The weekly workflow

**Files:**
- Create: `.github/workflows/hof.yml`

- [ ] **Step 1: Write the workflow**

`.github/workflows/hof.yml`:

```yaml
name: Hall of Records

on:
  schedule:
    # Tuesdays 11:00 UTC, September through January: after Monday night, before anyone is awake.
    - cron: '0 11 * 9-12,1 2'
  push:
    branches: [main]
    paths:
      - 'hof/**'
      - 'data/**'
      - 'src/bdfl/**'
      - '.github/workflows/hof.yml'
  workflow_dispatch:

# contents: write commits refreshed snapshots back to main; pages and id-token deploy the site.
permissions:
  contents: write
  pages: write
  id-token: write

# One run at a time, never cancelled mid-deploy.
concurrency:
  group: hof
  cancel-in-progress: false

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0
        with:
          python-version: '3.13'
          cache: pip
          cache-dependency-path: |
            hof/requirements.txt
            src/requirements.txt
      - run: pip install -r hof/requirements.txt

      - name: Fetch the current season from MFL
        run: python -m hof fetch

      # Pushes made with the built-in token never trigger other workflows, so this cannot
      # start the notifier's deploy or a second copy of this run.
      - name: Commit refreshed snapshots
        run: |
          if git diff --quiet -- data/raw; then
            echo "no snapshot changes"
          else
            git config user.name 'github-actions[bot]'
            git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
            git add data/raw
            git commit -m "data: MFL snapshots $(date -u +%F)"
            git push
          fi

      - name: Build the site
        run: python -m hof build --out dist

      - uses: actions/configure-pages@45bfe0192ca1faeb007ade9deae92b16b8254a0d # v6.0.0
      - uses: actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9 # v5.0.0
        with:
          path: dist
      - id: deployment
        uses: actions/deploy-pages@368f82528645a54fb793d4d04e342629a3f51346 # v5.0.1
```

- [ ] **Step 2: Check the YAML parses and the pins are real**

Run: `ruby -ryaml -e 'YAML.load_file(".github/workflows/hof.yml"); puts "ok"'`
Expected: `ok`. (macOS ships Ruby; on a machine without it, `python -c "import json,sys; ..."` cannot parse YAML, so install PyYAML in the venv for the check and do not add it to any requirements file.)

Run:

```bash
for pin in actions/configure-pages@45bfe0192ca1faeb007ade9deae92b16b8254a0d actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9 actions/deploy-pages@368f82528645a54fb793d4d04e342629a3f51346; do gh api "repos/${pin%@*}/commits/${pin#*@}" --jq '.sha[0:7] + " " + .commit.message' | head -1; done
```

Expected: three lines, each starting with the first seven characters of the pinned SHA. These were resolved from each action's latest release on 2026-09-07; if one is missing, resolve the current release tag with `gh api repos/<owner>/<repo>/releases/latest --jq .tag_name` and its commit with `gh api repos/<owner>/<repo>/git/ref/tags/<tag>`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/hof.yml
git commit -m "ci: weekly Hall of Records workflow with Pages deploy

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Rollout (owner steps after the PR merges)

1. Repository settings, Pages: set the source to **GitHub Actions**. Nothing deploys until this is done; the first run's deploy step fails with a clear message otherwise.
2. Actions, "Hall of Records", **Run workflow** on `main`. Watch the fetch step (about 25 MFL requests), the snapshot commit, and the deploy. The site appears at `https://btcookies.github.io/bdfl-trade-notifier/`.
3. Read through the franchise page for your own team and one player page. Anything that looks wrong is a template fix, not a data fix; the numbers were checked in Plan 2.
4. Set the Hall of Fame thresholds in `data/config.toml` if you have not already; pushing that change rebuilds and redeploys.
5. Plan 4 adds the Discord recap and wrap and the `notify` step to this workflow.
