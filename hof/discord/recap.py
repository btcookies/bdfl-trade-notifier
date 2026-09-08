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
