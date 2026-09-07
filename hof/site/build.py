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
