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
    fields.append(
        {"name": f"🏛 Hall of Fame · Class of {year}", "value": fit_lines(hall_lines(model, year), MAX_FIELD_VALUE)}
    )
    return {
        "title": f"🏆 {year} season wrap",
        "color": WRAP_COLOR,
        "description": truncate(description, MAX_DESCRIPTION),
        "fields": fields,
        "footer": {"text": f"Full records: {site_url}"},
    }
