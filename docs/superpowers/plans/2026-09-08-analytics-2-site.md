# Analytics Layer, Plan 2 of 3: Season Pages, Rivalries, and the Mobile Rework

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the analytics computed in Plan 1 (season pages with standings, luck, power rankings, and weekly awards; a rivalry grid; all-play and luck on franchise pages; season links on the home page) and make every page of the site usable on a phone.

**Architecture:** Three new Jinja templates and two new renderers in `hof/site/build.py`, small additions to the existing templates, and one stylesheet change. Column-priority classes (`p2`, `p3`), a sticky `key` column beside a fixed-width `rank` column, a pure-CSS scroll hint, and a reflowed head-to-head block handle phones without any JavaScript. Output stays deterministic.

**Tech Stack:** Python 3.13, Jinja2, one hand-written CSS file, pytest. Run from the repo root with the project venv active.

**Spec:** `docs/superpowers/specs/2026-09-08-analytics-layer-design.md`, sections 4 and 6. **Prerequisite:** Plan 1 (`2026-09-08-analytics-1-stats.md`) is merged: `Model` has `analytics` and `rivalries`, `SeasonRow`/`Totals` carry all-play and luck, `hof.stats.awards` exposes `AWARD_KEYS`, `format_value`, `labels_with`, and `Config` has `award_labels`.

**Conventions:**
- Site tests live in `tests/hof/test_hof_site.py` and use the module-scoped `built` fixture (a full build of the synthetic league into a temp dir) plus `read(out, relative)`.
- Franchise ids never appear in HTML. The rivalry grid's column headers are row numbers, never ids.
- Keep templates' existing style: `{% extends "base.html" %}`, the `pts`/`signed`/`pct` filters, `site.url(kind, key)` for every link.
- Run `ruff check hof tests` and `pytest` before every commit.

**Synthetic values used by the tests** (from Plan 1): 2020 standings order Gamma, Alpha, Delta, Beta; Alpha all-play 5-1-0, expected wins 1.67, luck −0.7; Delta luck +0.7; final power ranking Gamma 0.883 (▲1), Alpha 0.733 (▼1), Delta 0.267 (▲1), Beta 0.117 (▼1); awards leader Alpha with 15; Alpha's career awards 21 (15 in 2020, 6 in 2021), four of them `high_score`. Franchises index order Gamma, Alpha Prime, Delta, Beta. Alpha Prime vs Beta all-time 2-0.

---

### Task 1: URL kinds, nav entry, movement labels, and template filters

**Files:**
- Modify: `hof/site/build.py` (`SECTIONS`, `Site.url`, `environment()`)
- Modify: `hof/stats/power.py` (add `movement_label`)
- Modify: `hof/site/templates/base.html` (nav)
- Test: `tests/hof/test_hof_site.py`, `tests/hof/test_hof_power.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/hof/test_hof_power.py`:

```python
def test_movement_labels():
    assert [power.movement_label(m) for m in (None, 0, 2, -1)] == ["new", "–", "▲2", "▼1"]
```

Append to `tests/hof/test_hof_site.py`:

```python
def test_new_site_urls_and_nav(built):
    out, site, _ = built
    assert site.url("seasons") == "/hof/seasons/"
    assert site.url("season", 2020) == "/hof/seasons/2020/"
    assert site.url("rivalries") == "/hof/franchises/rivalries/"
    assert 'href="/hof/seasons/">Seasons</a>' in read(out, "")


def test_tint_runs_from_red_through_grey_to_green():
    from hof.site.build import tint

    assert tint((0, 0, 0)) == "#f4f4f4" and tint((1, 1, 0)) == "#f4f4f4" and tint((0, 0, 2)) == "#f4f4f4"
    assert tint((2, 0, 0)) == "#a3d9b0" and tint((0, 2, 0)) == "#e8a8a8"
    assert tint((3, 1, 0)) == "#cce7d2"  # halfway to green
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/hof/test_hof_power.py::test_movement_labels tests/hof/test_hof_site.py::test_new_site_urls_and_nav tests/hof/test_hof_site.py::test_tint_runs_from_red_through_grey_to_green -v`
Expected: 3 failed (`AttributeError`/`KeyError`/`ImportError`)

- [ ] **Step 3: Implement**

In `hof/stats/power.py`, append:

```python
def movement_label(movement: int | None) -> str:
    """▲n places gained, ▼n lost, – for no change, or "new" in the first ranked week."""
    if movement is None:
        return "new"
    if movement == 0:
        return "–"
    return f"▲{movement}" if movement > 0 else f"▼{-movement}"
```

In `hof/site/build.py`:

Add imports (keep isort order; `hof.stats` imports go together):

```python
from hof.stats import awards as awards_mod
from hof.stats import careers as careers_mod
from hof.stats import power
from hof.stats.awards import AWARD_KEYS
from hof.stats.careers import Career
from hof.stats.model import Model
from hof.stats.power import movement_label
```

Replace `SECTIONS` with:

```python
SECTIONS = {
    "home": "",
    "players": "players/",
    "franchises": "franchises/",
    "rivalries": "franchises/rivalries/",
    "seasons": "seasons/",
    "records": "records/",
    "hall": "hall-of-fame/",
    "drafts": "drafts/",
    "trades": "trades/",
}
```

In `Site.url`, add before `if kind == "static":`:

```python
        if kind == "season":
            return f"{self.base_path}seasons/{key}/"
```

Add a module-level function after `through_label`:

```python
def tint(cell: tuple[int, int, int]) -> str:
    """A hex color from neutral grey at .500 toward green (winning) or red (losing)."""
    wins, losses, ties = cell
    total = wins + losses + ties
    pct = (wins + 0.5 * ties) / total if total else 0.5
    strength = abs(pct - 0.5) * 2
    base = (244, 244, 244)
    target = (163, 217, 176) if pct >= 0.5 else (232, 168, 168)
    r, g, b = (int(base[i] + (target[i] - base[i]) * strength + 0.5) for i in range(3))
    return f"#{r:02x}{g:02x}{b:02x}"
```

In `environment()`, after `env.filters["mark"] = mark`, add:

```python
    env.filters["award"] = awards_mod.format_value
    env.filters["move"] = lambda line: movement_label(line.movement)
    env.filters["tint"] = tint
    env.filters["xw"] = lambda value: f"{value:.2f}"
    env.filters["score"] = lambda value: f"{value:.3f}"
```

and extend `env.globals.update(...)` with two more entries:

```python
        award_keys=AWARD_KEYS,
        award_labels=awards_mod.labels_with(config.award_labels),
        formula=power.FORMULA,
```

In `hof/site/templates/base.html`, change the nav to:

```html
  <nav>
    <a href="{{ site.url('players') }}">Players</a>
    <a href="{{ site.url('franchises') }}">Franchises</a>
    <a href="{{ site.url('seasons') }}">Seasons</a>
    <a href="{{ site.url('records') }}">Records</a>
    <a href="{{ site.url('hall') }}">Hall of Fame</a>
    <a href="{{ site.url('drafts') }}">Drafts</a>
    <a href="{{ site.url('trades') }}">Trades</a>
  </nav>
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/hof/test_hof_power.py tests/hof/test_hof_site.py -v`
Expected: the three new tests pass. `test_internal_links_resolve` now FAILS because the nav links to `/hof/seasons/`, which does not exist yet; Task 2 creates it. Every other site test passes.

- [ ] **Step 5: Lint and commit**

```bash
ruff check hof tests && git add hof/site/build.py hof/stats/power.py hof/site/templates/base.html tests/hof/test_hof_site.py tests/hof/test_hof_power.py && git commit -m "hof site: seasons and rivalries URL kinds, nav entry, analytics filters"
```

---

### Task 2: Seasons index and season pages

**Files:**
- Create: `hof/site/templates/seasons.html`, `hof/site/templates/season.html`
- Modify: `hof/site/build.py` (`SeasonSummary`, helpers, `render_seasons`, `RENDERERS`)
- Test: `tests/hof/test_hof_site.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/hof/test_hof_site.py`:

```python
def test_seasons_index_lists_newest_first(built):
    out, _, _ = built
    html = read(out, "seasons")
    assert 'href="/hof/seasons/2021/">2021</a>' in html and 'href="/hof/seasons/2020/">2020</a>' in html
    assert html.index('href="/hof/seasons/2021/"') < html.index('href="/hof/seasons/2020/"')
    assert ">Alpha<" in html and ">Gamma<" in html  # 2020 champion and runner-up by their 2020 names
    assert "2-0-0" in html and "33.0" in html  # best record and most points (Gamma)
    assert ">Delta</a> +0.7" in html  # luckiest
    assert ">Alpha</a> (15)" in html  # awards leader
    assert "through Week 1" in html  # 2021 has no champion yet


def test_season_page_for_a_finished_season(built):
    out, _, _ = built
    html = read(out, "seasons/2020")
    assert "<h1>2020 season" in html and "Final" in html
    assert "Alpha won the title, 30.0–20.0 over Gamma." in html
    names = re.findall(r'<td class="l key"><a href="/hof/franchises/[^"]+/">([^<]+)</a></td>', html)
    assert names[:4] == ["Gamma", "Alpha", "Delta", "Beta"]  # standings come first, in standings order
    assert "5-1-0" in html and "1.67" in html and "-0.7" in html and "+0.7" in html
    assert "Power rankings" in html and "through Week 2" in html
    assert "▲1" in html and "▼1" in html and "0.883" in html and "Score = 0.5 × all-play %" in html
    assert "<h3>Week 4" in html and "<h3>Week 1" in html and html.index("<h3>Week 4") < html.index("<h3>Week 1")
    assert "Highest score" in html and "would have gone 2-1-0 against the field" in html
    assert "Awards tally" in html and "<td>15</td>" in html


def test_season_page_for_the_season_in_progress(built):
    out, _, _ = built
    html = read(out, "seasons/2021")
    assert "through Week 1" in html and "won the title" not in html
    assert ">new<" in html  # first ranked week
    assert ">Alpha Prime</a>" in html
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/hof/test_hof_site.py -k season -v`
Expected: 3 failed with `FileNotFoundError` (no `seasons/index.html`)

- [ ] **Step 3: Write the templates**

`hof/site/templates/seasons.html`:

```html
{% extends "base.html" %}
{% block title %}Seasons{% endblock %}
{% block content %}
<h1>Seasons</h1>
<p class="lede">Standings with all-play and luck, power rankings, and the weekly awards, season by season.</p>
<div class="table-wrap">
<table>
  <thead><tr><th class="rank">Year</th><th class="l key">Champion</th><th class="l p2">Runner-up</th><th class="l p3">Best record</th><th class="l p3">Most points</th><th class="l p3">Luckiest</th><th class="l p3">Awards leader</th></tr></thead>
  <tbody>
  {% for s in seasons %}
  <tr>
    <td class="rank"><a href="{{ site.url('season', s.year) }}">{{ s.year }}</a></td>
    <td class="l key">{% if s.champion_id %}<a href="{{ site.url('franchise', s.champion_id) }}">{{ name_in(s.champion_id, s.year) }}</a>{% else %}<span class="muted">{{ s.state }}</span>{% endif %}</td>
    <td class="l p2">{% if s.runner_up_id %}<a href="{{ site.url('franchise', s.runner_up_id) }}">{{ name_in(s.runner_up_id, s.year) }}</a>{% endif %}</td>
    <td class="l p3">{% if s.best %}<a href="{{ site.url('franchise', s.best.franchise_id) }}">{{ s.best.name }}</a> {{ s.best.record }}{% endif %}</td>
    <td class="l p3">{% if s.most_points %}<a href="{{ site.url('franchise', s.most_points.franchise_id) }}">{{ s.most_points.name }}</a> {{ s.most_points.points_for|pts }}{% endif %}</td>
    <td class="l p3">{% if s.luckiest %}<a href="{{ site.url('franchise', s.luckiest.franchise_id) }}">{{ s.luckiest.name }}</a> {{ s.luckiest.luck|signed }}{% endif %}</td>
    <td class="l p3">{% for fid in s.leaders %}<a href="{{ site.url('franchise', fid) }}">{{ name_in(fid, s.year) }}</a>{{ ", " if not loop.last }}{% endfor %}{% if s.leaders %} ({{ s.leader_count }}){% endif %}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
</div>
{% endblock %}
```

`hof/site/templates/season.html`:

```html
{% extends "base.html" %}
{% block title %}{{ year }} season{% endblock %}
{% block content %}
<h1>{{ year }} season <small class="muted">{{ summary.state }}</small></h1>
{% if champion_line %}<p class="lede">{{ champion_line }}</p>{% endif %}

<h2>Standings</h2>
<p class="callout">All-play is each week's record against every other team's score. xW is the wins that all-play record would earn; luck is actual wins minus xW.</p>
{% if standings %}
<div class="table-wrap">
<table class="sortable">
  <thead><tr><th class="l key">Franchise</th><th>W-L-T</th><th>PF</th><th class="p2">PA</th><th class="p2">All-play</th><th class="p3">AP%</th><th class="p3">xW</th><th>Luck</th></tr></thead>
  <tbody>
  {% for s in standings %}
  <tr>
    <td class="l key"><a href="{{ site.url('franchise', s.franchise_id) }}">{{ s.name }}</a></td>
    <td>{{ s.record }}</td>
    <td>{{ s.points_for|pts }}</td>
    <td class="p2">{{ s.points_against|pts }}</td>
    <td class="p2">{{ s.allplay_record }}</td>
    <td class="p3">{{ s.allplay_pct|pct }}</td>
    <td class="p3">{{ s.expected_wins|xw }}</td>
    <td>{{ s.luck|signed }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
</div>
{% else %}
<p class="muted">No games yet.</p>
{% endif %}

{% if power %}
<h2>Power rankings <small class="muted">through Week {{ power_week }}</small></h2>
<div class="table-wrap">
<table>
  <thead><tr><th class="rank">#</th><th class="l key">Franchise</th><th>Move</th><th>Score</th><th class="p3">AP%</th><th class="p3">Win%</th><th class="p3">Form</th></tr></thead>
  <tbody>
  {% for p in power %}
  <tr>
    <td class="rank">{{ p.rank }}</td>
    <td class="l key"><a href="{{ site.url('franchise', p.franchise_id) }}">{{ p.name }}</a></td>
    <td>{{ p|move }}</td>
    <td>{{ p.score|score }}</td>
    <td class="p3">{{ p.allplay_pct|pct }}</td>
    <td class="p3">{{ p.win_pct|pct }}</td>
    <td class="p3">{{ p.form|pct }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
</div>
<p class="muted">{{ formula }}</p>
{% endif %}

<h2>Weekly awards</h2>
{% for w in weeks %}
<h3>Week {{ w.week }}{% if w.playoff %} <small>playoffs</small>{% endif %}</h3>
<ul class="awards">
  {% for a in w.awards %}
  <li><b>{{ a.label }}:</b>
    {% if a.key == "best_benched" %}{% if a.holder_id in site.player_slugs %}<a href="{{ site.url('player', a.holder_id) }}">{{ a.holder_name }}</a>{% else %}{{ a.holder_name }}{% endif %}{% else %}<a href="{{ site.url('franchise', a.franchise_id) }}">{{ a.holder_name }}</a>{% endif %},
    {{ a.value|award(a.unit) }}{% if a.detail %} <span class="muted">({{ a.detail }})</span>{% endif %}</li>
  {% endfor %}
</ul>
{% else %}
<p class="muted">No games yet.</p>
{% endfor %}

{% if tally %}
<h2>Awards tally</h2>
<div class="table-wrap">
<table class="sortable">
  <thead><tr><th class="l key">Franchise</th><th>Total</th>{% for key in award_keys %}<th class="p3">{{ award_labels[key] }}</th>{% endfor %}</tr></thead>
  <tbody>
  {% for row in tally %}
  <tr><td class="l key"><a href="{{ site.url('franchise', row.franchise_id) }}">{{ row.name }}</a></td><td>{{ row.total }}</td>{% for key in award_keys %}<td class="p3">{{ row.counts[key] or "" }}</td>{% endfor %}</tr>
  {% endfor %}
  </tbody>
</table>
</div>
{% endif %}
{% endblock %}
```

- [ ] **Step 4: Write the renderer**

In `hof/site/build.py`, add after `tint()`:

```python
@dataclass(frozen=True)
class SeasonSummary:
    """One row of the seasons index and the header of a season page."""

    year: int
    state: str  # "Final", "through Week n", or "No games yet"
    champion_id: str | None
    runner_up_id: str | None
    best: StandingLine | None  # best regular-season record, ties by points for
    most_points: StandingLine | None
    luckiest: StandingLine | None
    leaders: tuple[str, ...]  # franchise ids sharing the most awards
    leader_count: int


def season_summary(model: Model, year: int) -> SeasonSummary:
    season = model.league.season(year)
    stats = model.analytics[year]
    champion, runner_up = next(((c, r) for y, c, r in model.champions if y == year), (None, None))
    played = [line for line in stats.standings if line.games]
    if season.final is not None:
        state = "Final"
    elif stats.latest is not None:
        state = f"through Week {stats.latest.week}"
    else:
        state = "No games yet"
    return SeasonSummary(
        year=year,
        state=state,
        champion_id=champion,
        runner_up_id=runner_up,
        best=min(played, key=lambda s: (-(s.wins + 0.5 * s.ties) / s.games, -s.points_for, s.name), default=None),
        most_points=min(played, key=lambda s: (-s.points_for, s.name), default=None),
        luckiest=stats.luckiest,
        leaders=stats.awards_leaders,
        leader_count=stats.awards_leader_count,
    )


def champion_line(model: Model, year: int) -> str | None:
    final = model.league.season(year).final
    if final is None or final.winner is None or final.loser is None:
        return None
    winner = model.league.name_in(final.winner.franchise_id, year)
    loser = model.league.name_in(final.loser.franchise_id, year)
    return f"{winner} won the title, {final.winner.score or 0.0:.1f}–{final.loser.score or 0.0:.1f} over {loser}."


def tally_rows(model: Model, year: int) -> list[dict]:
    rows = [
        {"franchise_id": fid, "name": model.league.name_in(fid, year), "total": sum(counts.values()), "counts": counts}
        for fid, counts in model.analytics[year].tally.items()
    ]
    return sorted(rows, key=lambda r: (-r["total"], r["name"]))


def render_seasons(env: Environment, model: Model, site: Site) -> list[Page]:
    summaries = [season_summary(model, season.year) for season in reversed(model.league.seasons)]
    pages = [("seasons", env.get_template("seasons.html").render(seasons=summaries))]
    template = env.get_template("season.html")
    for summary in summaries:
        stats = model.analytics[summary.year]
        pages.append(
            (
                f"seasons/{summary.year}",
                template.render(
                    year=summary.year,
                    summary=summary,
                    champion_line=champion_line(model, summary.year),
                    standings=stats.standings,
                    power=stats.final_power,
                    power_week=stats.power_week,
                    weeks=list(reversed(stats.weeks)),
                    tally=tally_rows(model, summary.year) if stats.weeks else [],
                ),
            )
        )
    return pages
```

Add the import `from hof.stats.allplay import StandingLine` with the other `hof.stats` imports, and change `RENDERERS` to:

```python
RENDERERS: list[Renderer] = [render_home, render_players, render_franchises, render_seasons, render_records, render_hall, render_drafts, render_trades]
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/hof/test_hof_site.py -v`
Expected: the three season tests pass and `test_internal_links_resolve` passes again. `test_build_is_deterministic` and `test_no_franchise_id_reaches_the_html` still pass.

- [ ] **Step 6: Lint and commit**

```bash
ruff check hof tests && git add hof/site && git add tests/hof/test_hof_site.py && git commit -m "hof site: seasons index and season pages"
```

---

### Task 3: Rivalries page and its links

**Files:**
- Create: `hof/site/templates/rivalries.html`
- Modify: `hof/site/build.py` (`render_rivalries`, `RENDERERS`, `render_franchises` order)
- Modify: `hof/site/templates/franchises.html` (link below the table)
- Test: `tests/hof/test_hof_site.py`

- [ ] **Step 1: Update and add the failing tests**

In `tests/hof/test_hof_site.py`, `test_franchises_index_ranks_by_win_percentage`: the page gains a rivalries link after the table, so change `assert names == [...]` to `assert names[:4] == ["Gamma", "Alpha Prime", "Delta", "Beta"]`.

In `test_real_2020_fixture_builds_a_full_site`, the franchise page count must skip the new page. Change that assertion to:

```python
    assert sum(1 for name in pages if name.startswith("franchises/") and name not in ("franchises/index.html", "franchises/rivalries/index.html")) == 12
    assert "franchises/rivalries/index.html" in pages and "seasons/2020/index.html" in pages
```

Append:

```python
def test_rivalries_page(built):
    out, _, _ = built
    html = read(out, "franchises/rivalries")
    rows = re.findall(r'<td class="l key"><a href="/hof/franchises/([^"]+)/">', html)
    assert rows == ["gamma", "alpha-prime", "delta", "beta"]
    assert "<th>1</th><th>2</th><th>3</th><th>4</th>" in html
    assert 'href="/hof/franchises/alpha-prime/#h2h">2-0</a>' in html
    assert 'href="/hof/franchises/beta/#h2h">0-2</a>' in html
    assert 'class="self"' in html and "#a3d9b0" in html and "#e8a8a8" in html
    assert "Most played" in html and "Most lopsided" in html and "Most even" in html
    assert "Alpha Prime</a> 2-0 <a" in html and "2 meetings" in html
    assert "Nobody has met 5 times yet." in html
    assert 'href="/hof/franchises/rivalries/"' in read(out, "franchises")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/hof/test_hof_site.py -k "rivalries or franchises_index or real_2020" -v`
Expected: `test_rivalries_page` and `test_real_2020_fixture_builds_a_full_site` FAIL

- [ ] **Step 3: Write the template and renderer**

`hof/site/templates/rivalries.html`:

```html
{% extends "base.html" %}
{% block title %}Rivalries{% endblock %}
{% block content %}
{% macro pair(p) %}<a href="{{ site.url('franchise', p.a_id) }}">{{ p.a_name }}</a> {{ p.record }} <a href="{{ site.url('franchise', p.b_id) }}">{{ p.b_name }}</a> <span class="muted">· {{ p.meetings }} meeting{{ 's' if p.meetings != 1 }}</span>{% endmacro %}
<h1>Rivalries</h1>
<p class="lede">Every franchise against every other, all-time, by current name. Read a row left to right: that franchise's wins and losses against each numbered column.</p>
<div class="table-wrap">
<table class="grid">
  <thead><tr><th class="rank">#</th><th class="l key">Franchise</th>{% for fid in grid.order %}<th>{{ loop.index }}</th>{% endfor %}</tr></thead>
  <tbody>
  {% for row_id in grid.order %}
  <tr>
    <td class="rank">{{ loop.index }}</td>
    <td class="l key"><a href="{{ site.url('franchise', row_id) }}">{{ current_name(row_id) }}</a></td>
    {% for col_id in grid.order %}
    {% set cell = grid.cells.get((row_id, col_id)) %}
    {% if row_id == col_id %}<td class="self"></td>
    {% elif cell %}<td class="cell" style="background:{{ cell|tint }}"><a href="{{ site.url('franchise', row_id) }}#h2h">{{ cell[0] }}-{{ cell[1] }}{% if cell[2] %}-{{ cell[2] }}{% endif %}</a></td>
    {% else %}<td class="cell"></td>{% endif %}
    {% endfor %}
  </tr>
  {% endfor %}
  </tbody>
</table>
</div>

<div class="two">
  <div>
    <h2>Most played</h2>
    <ol class="leaders">{% for p in grid.most_played %}<li>{{ pair(p) }}</li>{% endfor %}</ol>
  </div>
  <div>
    <h2>Most lopsided</h2>
    {% if grid.most_lopsided %}<ol class="leaders">{% for p in grid.most_lopsided %}<li>{{ pair(p) }}</li>{% endfor %}</ol>{% else %}<p class="muted">Nobody has met {{ min_meetings }} times yet.</p>{% endif %}
    <h2>Most even</h2>
    {% if grid.most_even %}<ol class="leaders">{% for p in grid.most_even %}<li>{{ pair(p) }}</li>{% endfor %}</ol>{% else %}<p class="muted">Nobody has met {{ min_meetings }} times yet.</p>{% endif %}
  </div>
</div>
{% endblock %}
```

In `hof/site/build.py`, add the import `from hof.stats.rivalries import MIN_MEETINGS, ranked` with the other `hof.stats` imports, then:

```python
def render_rivalries(env: Environment, model: Model, site: Site) -> list[Page]:
    html = env.get_template("rivalries.html").render(grid=model.rivalries, min_meetings=MIN_MEETINGS)
    return [("franchises/rivalries", html)]
```

Change the first line of `render_franchises` to use the shared order:

```python
    histories = ranked(model.histories)
```

Add `render_rivalries` to `RENDERERS` right after `render_franchises`.

In `hof/site/templates/franchises.html`, add after the closing `</div>` of the table wrap:

```html
<p><a href="{{ site.url('rivalries') }}">Rivalry grid: every franchise against every other</a></p>
```

Add to `hof/site/static/site.css` (after the `.h2h` rules):

```css
table.grid td.cell { text-align: center; min-width: 3.2em; }
table.grid td.cell a { color: var(--ink); }
table.grid td.self { background: var(--line); }
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/hof/test_hof_site.py -v`
Expected: all passed

- [ ] **Step 5: Lint and commit**

```bash
ruff check hof tests && git add hof/site tests/hof/test_hof_site.py && git commit -m "hof site: rivalry grid page"
```

---

### Task 4: Franchise page and home page additions

**Files:**
- Modify: `hof/site/templates/franchise.html` (full rewrite below), `hof/site/templates/home.html`
- Modify: `hof/site/build.py` (`franchise_awards`, `render_franchises`, `render_home`)
- Test: `tests/hof/test_hof_site.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/hof/test_hof_site.py`:

```python
def test_franchise_page_has_all_play_luck_awards_and_rivalry_link(built):
    out, _, _ = built
    html = read(out, "franchises/alpha-prime")
    assert "<b>.857</b><span>All-play</span>" in html
    assert "<b>-0.7</b><span>Luck</span>" in html
    assert "Weekly awards: 21" in html and "Highest score 4" in html and 'href="/hof/seasons/"' in html
    assert '<h2 id="h2h">' in html and 'href="/hof/franchises/rivalries/"' in html
    assert "<th>Luck</th>" in html and '<th class="p2">All-play</th>' in html
    assert 'href="/hof/seasons/2020/">2020</a>' in html
    assert "<td class=\"p2\">5-1-0</td>" in html and "<td>-0.7</td>" in html
    assert 'data-label="Reg">' in html
    for details in re.findall(r"<details>.*?</details>", html, re.S):
        assert '<div class="table-wrap">' in details
    beta = read(out, "franchises/beta")
    assert "Weekly awards: 6" in beta  # 4 in 2020, 2 in 2021


def test_home_links_seasons_and_shows_the_season_in_progress(built):
    out, _, _ = built
    html = read(out, "")
    assert 'href="/hof/seasons/2020/">2020</a>' in html
    assert "<b>2021</b> · through Week 1 ·" in html and 'href="/hof/seasons/2021/"' in html
    assert '<td class="l key"><a href="/hof/franchises/alpha-prime/">Alpha</a></td>' in html
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/hof/test_hof_site.py -k "franchise_page_has or home_links" -v`
Expected: 2 failed

- [ ] **Step 3: Rewrite `hof/site/templates/franchise.html`**

Replace the whole file with the following. Besides the new stats, it carries the mobile classes and data labels from spec section 6 so this template is touched once.

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
  <div><b>{{ h.totals.allplay_pct|pct }}</b><span>All-play</span></div>
  <div><b>{{ h.totals.luck|signed }}</b><span>Luck</span></div>
  <div><b>{{ h.streak or "—" }}</b><span>Streak</span></div>
</div>
{% if awards_line %}
<p class="muted">Weekly awards: {{ awards_line.total }} · {% for label, n in awards_line.counts %}{{ label }} {{ n }}{{ ", " if not loop.last }}{% endfor %} · <a href="{{ site.url('seasons') }}">by season</a></p>
{% endif %}

<h2>Season by season</h2>
{% for summary in h.eras %}
<div class="era{% if not loop.first %} old{% endif %}">
  <h3>As {{ summary.era.name }} <small>{{ years(summary.era.first_year, summary.era.last_year) }} · {{ summary.totals.record }} · {{ summary.totals.titles }} title{{ 's' if summary.totals.titles != 1 }}</small></h3>
  <div class="table-wrap">
  <table>
    <thead><tr><th class="key">Year</th><th>W-L-T</th><th class="p3">Div</th><th>PF</th><th class="p2">PA</th><th class="p2">All-play</th><th>Luck</th><th class="p3">Seed</th><th class="l">Finish</th><th class="l p3">Top starter</th></tr></thead>
    <tbody>
    {% for row in summary.rows %}
    <tr>
      <td class="key"><a href="{{ site.url('season', row.year) }}">{{ row.year }}</a></td>
      <td>{{ row.wins }}-{{ row.losses }}-{{ row.ties }}</td>
      <td class="p3">{{ row.division_record }}</td>
      <td>{{ row.points_for|pts }}</td>
      <td class="p2">{{ row.points_against|pts }}</td>
      <td class="p2">{{ row.allplay[0] }}-{{ row.allplay[1] }}-{{ row.allplay[2] }}</td>
      <td>{{ row.luck|signed }}</td>
      <td class="p3">{{ row.seed or "–" }}</td>
      <td class="l">{% if row.title %}🏆 {% endif %}{{ row.finish }}</td>
      <td class="l p3">{% if row.top_starter %}<a href="{{ site.url('player', row.top_starter[0]) }}">{{ row.top_starter[1] }}</a> {{ row.top_starter[2]|pts }}{% endif %}</td>
    </tr>
    {% endfor %}
    <tr class="sub">
      <td class="key">Era</td><td>{{ summary.totals.record }}</td><td class="p3"></td>
      <td>{{ summary.totals.points_for|pts }}</td><td class="p2">{{ summary.totals.points_against|pts }}</td>
      <td class="p2">{{ summary.totals.allplay_record }}</td><td>{{ summary.totals.luck|signed }}</td><td class="p3"></td>
      <td class="l">{{ summary.totals.titles }} title{{ 's' if summary.totals.titles != 1 }} · {{ summary.totals.playoff_apps }} playoff app{{ 's' if summary.totals.playoff_apps != 1 }}</td><td class="l p3"></td>
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
      <thead><tr><th class="rank">#</th><th class="l key">Player</th><th>Pos</th><th class="p3">Yrs</th><th class="p2">GS</th><th>Pts</th><th>VOR</th></tr></thead>
      <tbody>
      {% for t in top %}
      <tr><td class="rank">{{ loop.index }}</td><td class="l key"><a href="{{ site.url('player', t.player_id) }}">{{ t.name }}</a></td><td>{{ t.position }}</td><td class="p3">{{ years(t.first_year, t.last_year) }}</td><td class="p2">{{ t.starts }}</td><td>{{ t.points|pts }}</td><td>{{ t.vor|pts }}</td></tr>
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
      <thead><tr><th>Year</th><th class="l p3">Round</th><th class="l">Opponent</th><th>Score</th><th>Res</th></tr></thead>
      <tbody>
      {% for m in h.playoff_games %}
      <tr><td>{{ m.year }}</td><td class="l p3">{{ m.round_name }}</td><td class="l"><a href="{{ site.url('franchise', m.opponent_id) }}">{{ m.opponent_name }}</a></td><td>{{ m.own_score|pts }}–{{ m.opponent_score|pts }}</td><td>{{ m.result }}{% if m.result == "W" and m.round_name == "Final" %} 🏆{% endif %}</td></tr>
      {% endfor %}
      </tbody>
    </table>
    </div>
    {% else %}<p class="muted">No playoff games yet.</p>{% endif %}
  </div>
</div>

<h2 id="h2h">Head-to-head <small><a href="{{ site.url('rivalries') }}">Rivalry grid</a></small></h2>
<p class="callout">All-time series against every other franchise, by their current name. Open a row for every meeting, with the names both teams used at the time.</p>
<div class="h2h">
  <div class="head"><span>Opponent</span><span>All-time</span><span>Reg</span><span>Playoffs</span><span>PF</span><span>PA</span><span>Margin</span><span>Streak</span><span>Last meeting</span></div>
  {% for s in h.series %}
  <details>
    <summary>
      <span><a href="{{ site.url('franchise', s.opponent_id) }}">{{ s.opponent_name }}</a></span>
      <span>{{ s.wins }}-{{ s.losses }}-{{ s.ties }}</span>
      <span data-label="Reg">{{ s.regular[0] }}-{{ s.regular[1] }}-{{ s.regular[2] }}</span>
      <span data-label="Playoffs">{% if s.playoff[0] + s.playoff[1] + s.playoff[2] %}{{ s.playoff[0] }}-{{ s.playoff[1] }}{% else %}–{% endif %}</span>
      <span data-label="PF">{{ s.points_for|pts }}</span>
      <span data-label="PA">{{ s.points_against|pts }}</span>
      <span data-label="Margin">{{ s.avg_margin|signed }}</span>
      <span data-label="Streak">{{ s.streak }}</span>
      <span data-label="Last">{% if s.last %}{{ s.last.year }} {{ s.last.round_name or ("Wk " ~ s.last.week) }}, {{ s.last.result }} {{ s.last.own_score|pts }}–{{ s.last.opponent_score|pts }}{% endif %}</span>
    </summary>
    <div class="table-wrap">
    <table>
      <thead><tr><th>Year</th><th>Wk</th><th class="l p3">Round</th><th class="l p3">As</th><th class="l">Opponent</th><th>Score</th><th>Res</th></tr></thead>
      <tbody>
      {% for m in s.meetings|reverse %}
      <tr><td>{{ m.year }}</td><td>{{ m.week }}</td><td class="l p3">{{ m.round_name or "" }}</td><td class="l p3">{{ m.own_name }}</td><td class="l">{{ m.opponent_name }}</td><td>{{ m.own_score|pts }}–{{ m.opponent_score|pts }}</td><td>{{ m.result }}</td></tr>
      {% endfor %}
      </tbody>
    </table>
    </div>
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
      <thead><tr><th class="p3">Date</th><th class="l key">With</th><th class="l">Got</th><th class="l">Gave</th><th class="l p2">Verdict</th></tr></thead>
      <tbody>
      {% for t in trades %}
      {% set own = t.sides[0] if t.sides[0].franchise_id == h.id else t.sides[1] %}
      {% set other = t.sides[1] if t.sides[0].franchise_id == h.id else t.sides[0] %}
      <tr>
        <td class="p3"><a href="{{ site.url('trades') }}#t{{ t.year }}-{{ t.timestamp }}">{{ t.timestamp|date }}</a></td>
        <td class="l key"><a href="{{ site.url('franchise', other.franchise_id) }}">{{ other.name }}</a></td>
        <td class="l">{% for a in own.received %}{{ a.label }}{{ "; " if not loop.last }}{% endfor %}</td>
        <td class="l">{% for a in other.received %}{{ a.label }}{{ "; " if not loop.last }}{% endfor %}</td>
        <td class="l p2">{{ t.verdict }}</td>
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

- [ ] **Step 4: Update `hof/site/templates/home.html`**

Replace the Champions section with:

```html
<section>
  {% if current %}
  <p class="callout"><b>{{ current.year }}</b> · {{ current.state }} · <a href="{{ site.url('season', current.year) }}">Standings, power rankings, and awards</a></p>
  {% endif %}
  <h2>Champions</h2>
  <div class="table-wrap">
  <table>
    <thead><tr><th class="rank">Year</th><th class="l key">Champion</th><th class="l">Runner-up</th></tr></thead>
    <tbody>
    {% for year, champion, runner_up in champions %}
    <tr>
      <td class="rank"><a href="{{ site.url('season', year) }}">{{ year }}</a></td>
      <td class="l key"><a href="{{ site.url('franchise', champion) }}">{{ name_in(champion, year) }}</a></td>
      <td class="l"><a href="{{ site.url('franchise', runner_up) }}">{{ name_in(runner_up, year) }}</a></td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
</section>
```

- [ ] **Step 5: Update the renderers in `hof/site/build.py`**

Add after `tally_rows`:

```python
def franchise_awards(model: Model, franchise_id: str, labels: dict[str, str]) -> dict | None:
    """Career award counts for the franchise page line, or None when it has none."""
    counts = dict.fromkeys(AWARD_KEYS, 0)
    for stats in model.analytics.values():
        for key, n in stats.tally.get(franchise_id, {}).items():
            counts[key] += n
    total = sum(counts.values())
    if not total:
        return None
    return {"total": total, "counts": [(labels[key], counts[key]) for key in AWARD_KEYS if counts[key]]}


def current_season(model: Model) -> SeasonSummary | None:
    """The newest season while it is in progress and has a counted game; else None."""
    newest = model.league.latest
    if newest.complete or model.analytics[newest.year].latest is None:
        return None
    return season_summary(model, newest.year)
```

In `render_franchises`, add `awards_line=franchise_awards(model, history.id, env.globals["award_labels"]),` to the `template.render(...)` call (after `top=...`).

In `render_home`, add `"current": current_season(model),` to `context`.

- [ ] **Step 6: Run the tests**

Run: `pytest tests/hof/test_hof_site.py -v`
Expected: all passed, including `test_franchise_page_groups_seasons_by_era` (it still finds `<b>2-1-0</b>`, `<summary>`, and `>Beta<`).

- [ ] **Step 7: Lint and commit**

```bash
ruff check hof tests && git add hof/site tests/hof/test_hof_site.py && git commit -m "hof site: all-play, luck, and awards on franchise pages; season links on the home page"
```

---

### Task 5: Mobile: column priority, sticky key column, scroll hint, head-to-head reflow

**Files:**
- Modify: `hof/site/static/site.css`
- Modify: `hof/site/templates/players.html`, `player.html`, `franchises.html`, `records.html`, `hall.html`, `drafts.html`, `draft.html`
- Test: `tests/hof/test_hof_site.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/hof/test_hof_site.py`:

```python
def test_priority_and_key_classes_are_on_every_wide_table(built):
    out, _, _ = built
    assert '<th class="l key">Player</th><th>Pos</th><th class="p3">Years</th>' in read(out, "players")
    assert '<th class="rank">#</th><th class="l key">Holder</th><th>Mark</th><th class="l p2">Detail</th>' in read(out, "records")
    assert '<th class="key">Year</th><th class="l">Franchise</th><th>GS</th><th>Pts</th><th>VOR</th><th class="p2">Bench</th>' in read(out, "players/qb-a1-a1")
    assert '<th class="l key">Franchise</th><th>Record</th><th class="p2">Pct</th>' in read(out, "franchises")
    assert '<th class="l key">Player</th><th>Pos</th><th class="p3">GS</th>' in read(out, "hall-of-fame")
    css = (out / "static" / "site.css").read_text()
    assert "@media (max-width: 720px) { .p3 { display: none; } }" in css
    assert "@media (max-width: 480px) { .p2 { display: none; } }" in css
    assert "position: sticky" in css and "background-attachment: local" in css
    assert 'span[data-label]::before { content: attr(data-label) " "; }' in css
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/hof/test_hof_site.py::test_priority_and_key_classes_are_on_every_wide_table -v`
Expected: FAIL on the players assertion

- [ ] **Step 3: Mark the columns in each template**

`players.html`: replace the `<thead>` line and the row cells with:

```html
  <thead><tr><th class="l key">Player</th><th>Pos</th><th class="p3">Years</th><th class="l p3">Franchises</th><th>GS</th><th>Pts</th><th>VOR</th><th class="p2">Titles</th><th class="p3">Active</th></tr></thead>
  <tbody>
  {% for c in careers %}
  <tr data-name="{{ c.name|lower }}">
    <td class="l key"><a href="{{ site.url('player', c.player_id) }}">{{ c.name }}</a></td>
    <td>{{ c.position }}</td>
    <td class="p3">{% if c.first_year == c.last_year %}{{ c.first_year }}{% else %}{{ c.first_year }}–{{ c.last_year }}{% endif %}</td>
    <td class="l p3">{% for fid in c.franchise_ids %}<a href="{{ site.url('franchise', fid) }}">{{ current_name(fid) }}</a>{{ ", " if not loop.last }}{% endfor %}</td>
    <td>{{ c.starts }}</td>
    <td>{{ c.points|pts }}</td>
    <td>{{ c.vor|pts }}</td>
    <td class="p2">{{ c.titles }}</td>
    <td class="p3">{{ "Yes" if c.active else "" }}</td>
  </tr>
  {% endfor %}
  </tbody>
```

`player.html`, the season table:

```html
  <thead><tr><th class="key">Year</th><th class="l">Franchise</th><th>GS</th><th>Pts</th><th>VOR</th><th class="p2">Bench</th><th class="p3">PO GS</th><th class="p3">PO Pts</th><th class="p2">Title</th></tr></thead>
  <tbody>
  {% for line in career.seasons %}
  <tr>
    <td class="key">{{ line.year }}</td>
    <td class="l">{% for fid in line.franchise_ids %}<a href="{{ site.url('franchise', fid) }}">{{ name_in(fid, line.year) }}</a>{{ ", " if not loop.last }}{% endfor %}</td>
    <td>{{ line.starts }}</td>
    <td>{{ line.points|pts }}</td>
    <td>{{ line.vor|pts }}</td>
    <td class="p2">{{ line.bench_points|pts }}</td>
    <td class="p3">{{ line.playoff_starts }}</td>
    <td class="p3">{{ line.playoff_points|pts }}</td>
    <td class="p2">{{ "🏆" if line.title }}</td>
  </tr>
  {% endfor %}
  <tr class="sub">
    <td class="key">Career</td><td class="l"></td>
    <td>{{ career.starts }}</td><td>{{ career.points|pts }}</td><td>{{ career.vor|pts }}</td><td class="p2">{{ career.bench_points|pts }}</td>
    <td class="p3">{{ career.playoff_starts }}</td><td class="p3">{{ career.playoff_points|pts }}</td><td class="p2">{{ career.titles or "" }}</td>
  </tr>
  </tbody>
```

`franchises.html`, the table:

```html
  <thead><tr><th class="l key">Franchise</th><th>Record</th><th class="p2">Pct</th><th class="p3">PF</th><th class="p3">PA</th><th class="p3">Playoffs</th><th class="p2">PO record</th><th>Titles</th><th class="p3">Streak</th></tr></thead>
  <tbody>
  {% for h in histories %}
  <tr>
    <td class="l key"><a href="{{ site.url('franchise', h.id) }}">{{ h.name }}</a></td>
    <td>{{ h.totals.record }}</td>
    <td class="p2">{{ h.totals.win_pct|pct }}</td>
    <td class="p3">{{ h.totals.points_for|pts }}</td>
    <td class="p3">{{ h.totals.points_against|pts }}</td>
    <td class="p3">{{ h.totals.playoff_apps }}</td>
    <td class="p2">{{ h.totals.playoff_wins }}-{{ h.totals.playoff_losses }}</td>
    <td>{{ h.totals.titles }}</td>
    <td class="p3">{{ h.streak }}</td>
  </tr>
  {% endfor %}
  </tbody>
```

`records.html`, the table inside the loop:

```html
      <thead><tr><th class="rank">#</th><th class="l key">Holder</th><th>Mark</th><th class="l p2">Detail</th></tr></thead>
      <tbody>
      {% for e in table.entries %}
      <tr>
        <td class="rank">{{ loop.index }}</td>
        <td class="l key">{% if e.player_id and e.player_id in site.player_slugs %}<a href="{{ site.url('player', e.player_id) }}">{{ e.holder }}</a>{% elif e.franchise_id %}<a href="{{ site.url('franchise', e.franchise_id) }}">{{ e.holder }}</a>{% else %}{{ e.holder }}{% endif %}</td>
        <td>{{ e.value|mark(table.unit) }}</td>
        <td class="l p2">{{ e.detail }}{% if e.playoff and table.group.endswith("single game") %} <span class="pos">PO</span>{% endif %}</td>
      </tr>
      {% endfor %}
      </tbody>
```

`hall.html`, the watch list table:

```html
  <thead><tr><th class="l key">Player</th><th>Pos</th><th class="p3">GS</th><th>VOR</th><th>Needs</th></tr></thead>
  <tbody>
  {% for w in hall.watch_list %}
  <tr>
    <td class="l key"><a href="{{ site.url('player', w.player_id) }}">{{ w.name }}</a></td>
    <td>{{ w.position }}</td>
    <td class="p3">{{ w.starts }}</td>
    <td>{{ w.vor|pts }}</td>
    <td>{{ w.needed_vor|pts }}{% if w.needed_starts %} and {{ w.needed_starts }} start{{ 's' if w.needed_starts != 1 }}{% endif %}</td>
  </tr>
  {% endfor %}
  </tbody>
```

`drafts.html`: the rankings table header becomes `<thead><tr><th class="l key">Franchise</th><th>Picks</th><th>VOR from picks</th></tr></thead>` and its first cell `<td class="l key">`; the by-year table header becomes `<thead><tr><th>Year</th><th class="p3">Rounds</th><th class="l">Steal</th><th class="l">Bust</th></tr></thead>` and the rounds cell `<td class="p3">{{ d.rounds }}</td>`.

`draft.html`, the picks table:

```html
  <thead><tr><th class="rank">Pick</th><th class="l key">Team</th><th class="l p3">Via</th><th class="l">Player</th><th>Pos</th><th class="p3">GS</th><th>Pts</th><th>VOR</th><th class="p2">Career pts</th><th class="p2">Career VOR</th></tr></thead>
  <tbody>
  {% for p in d.picks %}
  <tr>
    <td class="rank" data-sort="{{ p.round * 100 + p.pick }}">{{ p.round }}.{{ "%02d"|format(p.pick) }}</td>
    <td class="l key"><a href="{{ site.url('franchise', p.franchise_id) }}">{{ p.franchise_name }}</a></td>
    <td class="l p3">{% if p.original_owner_id and p.original_owner_id != p.franchise_id %}{{ name_in(p.original_owner_id, p.year) }}{% endif %}</td>
    <td class="l">{% if p.player_id in site.player_slugs %}<a href="{{ site.url('player', p.player_id) }}">{{ p.player_name }}</a>{% else %}{{ p.player_name }}{% endif %}</td>
    <td>{{ p.position }}</td>
    <td class="p3">{{ p.starts_for }}</td>
    <td>{{ p.points_for|pts }}</td>
    <td>{{ p.vor_for|pts }}</td>
    <td class="p2">{{ p.career_points|pts }}</td>
    <td class="p2">{{ p.career_vor|pts }}</td>
  </tr>
  {% endfor %}
  </tbody>
```

- [ ] **Step 4: Update the stylesheet**

In `hof/site/static/site.css`, delete the line `.h2h details table { margin: 4px 0 8px 12px; width: auto; }` and append this block at the end of the file:

```css
/* --- phones ------------------------------------------------------------- */
/* Column priority: p3 columns hide first, p2 columns on the narrowest phones. */
@media (max-width: 720px) { .p3 { display: none; } }
@media (max-width: 480px) { .p2 { display: none; } }

/* A key column sticks while the rest of a wide table scrolls beneath it. A rank/year column
   before it has a fixed width and sticks too, so the two sit side by side. */
:root { --rank-w: 3.6em; }
th.rank, td.rank { width: var(--rank-w); min-width: var(--rank-w); }
.table-wrap th.key, .table-wrap td.key, .table-wrap th.rank, .table-wrap td.rank { position: sticky; left: 0; z-index: 1; background: var(--bg); }
.table-wrap th.key, .table-wrap th.rank { background: #f0f0f0; }
.table-wrap tr.sub td.key, .table-wrap tr.sub td.rank { background: #fafafa; }
.table-wrap th.rank + th.key, .table-wrap td.rank + td.key { left: var(--rank-w); }

/* Scroll hint: an inner shadow on whichever edge has more table beyond it. */
.table-wrap {
  background:
    linear-gradient(to right, var(--bg) 30%, rgba(255, 255, 255, 0)),
    linear-gradient(to left, var(--bg) 30%, rgba(255, 255, 255, 0)) 100% 0,
    radial-gradient(farthest-side at 0 50%, rgba(0, 0, 0, .18), rgba(0, 0, 0, 0)),
    radial-gradient(farthest-side at 100% 50%, rgba(0, 0, 0, .18), rgba(0, 0, 0, 0)) 100% 0;
  background-repeat: no-repeat;
  background-size: 40px 100%, 40px 100%, 14px 100%, 14px 100%;
  background-attachment: local, local, scroll, scroll;
}
.h2h details .table-wrap { margin: 4px 0 8px 12px; }
.h2h details table { width: auto; }
.awards li { margin: 3px 0; }

@media (max-width: 720px) {
  th, td { padding: 8px 7px; }
  .h2h .head { display: none; }
  .h2h summary { display: flex; flex-wrap: wrap; gap: 2px 12px; padding: 9px 7px; }
  .h2h summary span { text-align: left; font-size: 12px; color: var(--muted); }
  .h2h summary span:first-child { flex: 1 1 calc(100% - 100px); font-size: 14px; color: inherit; }
  .h2h summary span:nth-child(2) { flex: 0 0 80px; text-align: right; font-size: 14px; font-weight: 600; color: inherit; }
  .h2h summary span[data-label]::before { content: attr(data-label) " "; }
  .h2h details .table-wrap { margin-left: 0; }
}
```

- [ ] **Step 5: Run the whole suite**

Run: `pytest && ruff check hof tests`
Expected: all passed. `test_players_index_lists_every_career_sorted_by_value` still finds its `data-name` attributes; `test_records_page_has_every_table` still finds its links; the sorting script indexes cells by position, and hidden cells stay in the DOM, so sorting is unaffected.

- [ ] **Step 6: Commit**

```bash
git add hof/site tests/hof/test_hof_site.py && git commit -m "hof site: column priority, sticky key column, scroll hint, head-to-head reflow for phones"
```

---

### Task 6: Acceptance: real-data build and the 375-pixel width check

**Files:** none changed unless the check fails.

- [ ] **Step 1: Build the real site into a preview directory**

```bash
python -m hof build --out preview/bdfl-trade-notifier && python -m http.server -d preview 8765
```

(`preview/` is gitignored. In the Claude Code desktop app, prefer the in-app browser's `preview_start` with a launch config that runs the same `http.server` command; a plain background `http.server` is fine elsewhere.)

- [ ] **Step 2: Run the width check on every page type at 375 px**

In the browser, set the viewport to the mobile preset (375 × 812) and, for each URL below under `http://localhost:8765/bdfl-trade-notifier/`, run this JavaScript and record the result:

```javascript
({page: location.pathname, tooWide: document.documentElement.scrollWidth > document.documentElement.clientWidth, width: document.documentElement.scrollWidth})
```

Pages: `/`, `players/`, the first player page linked from it, `franchises/`, the first franchise page linked from it (then click the first head-to-head `<summary>` to expand a series and run the check again), `franchises/rivalries/`, `seasons/`, `seasons/2026/`, `seasons/2020/`, `records/`, `hall-of-fame/`, `drafts/`, `drafts/2020/`, `trades/`.

Expected: `tooWide` is `false` on every page, including the franchise page with a series expanded. If any page is wider than the viewport, find the offending element with:

```javascript
[...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right > document.documentElement.clientWidth + 1).slice(0, 5).map(e => e.tagName + '.' + e.className)
```

and fix the template or stylesheet (usually a table outside a `.table-wrap`, or a `.h2h` element), then rebuild and re-run. Also confirm visually that the records tables show the Mark column without scrolling, that the players list shows GS, Pts, and VOR, and that expanding a head-to-head row shows a scrollable meetings table inside the page.

- [ ] **Step 3: Reset the viewport and stop the server**

Set the browser back to the desktop preset and stop the `http.server` process.

- [ ] **Step 4: Commit any fixes**

```bash
git add hof/site && git commit -m "hof site: mobile width fixes from the 375px check"
```

(Skip when nothing changed.)

---

## Done when

- `pytest` passes and `ruff check hof tests` is clean.
- `/seasons/`, `/seasons/<year>/` for every season, and `/franchises/rivalries/` render and are linked from the nav, the franchises index, franchise pages, and the home page.
- Franchise pages show all-play and luck per season and all-time, plus an awards line.
- Every page passes the 375-pixel width check with no sideways page scroll.

Plan 3 (`2026-09-08-analytics-3-discord.md`) adds the second recap embed and the wrap lines.
