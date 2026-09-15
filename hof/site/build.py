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
from hof.stats import careers as careers_mod
from hof.stats.careers import Career
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

    def mark(value: float, unit: str) -> str:
        if unit in ("starts", "games", "titles"):
            return str(int(value))
        if unit == "wins":
            return f"{value:+.1f}"
        if unit == "pct":
            return "1.000" if value >= 1 else f"{value:.3f}"[1:]
        return f"{value:.1f}"

    env.filters["mark"] = mark
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


RENDERERS: list[Renderer] = [render_home, render_players, render_franchises, render_records, render_hall, render_drafts, render_trades]


def write_page(out: Path, relative: str, html: str) -> None:
    target = (out / relative if relative else out) / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")


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
