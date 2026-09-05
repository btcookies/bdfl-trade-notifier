"""Build Discord embeds, stored details, and summaries for trades and waiver claims."""

from __future__ import annotations

import re
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

MARKDOWN_SPECIALS = re.compile(r"([\\*_~`|>])")

T = TypeVar("T")


def escape_markdown(text: str) -> str:
    """Backslash-escape characters Discord would render as markdown."""
    return MARKDOWN_SPECIALS.sub(r"\\\1", text)


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
        bullets = "\n".join(f"• {escape_markdown(asset)}" for asset in side["assets"]) or "• (nothing)"
        fields.append(
            {
                "name": truncate(f"{escape_markdown(side['franchise_name'])} gives up", MAX_TITLE),
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
    franchise_name = escape_markdown(details["franchise_name"])
    if details["added"] is None:
        raw_transaction = escape_markdown(details["raw_transaction"])
        return f"**{franchise_name}** claim could not be parsed: `{raw_transaction}`"
    line = f"**{franchise_name}** won **{escape_markdown(details['added'])}** for {details['bid']}"
    if details["dropped"]:
        line += f" · dropped {escape_markdown(details['dropped'])}"
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
