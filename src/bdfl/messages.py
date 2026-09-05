"""Build Discord embeds, stored details, and summaries for trades and waiver claims."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from bdfl.assets import format_dollars, player_label, render_asset
from bdfl.models import LeagueInfo, Player, Trade, WaiverClaim

TRADE_COLOR = 0xE74C3C
WAIVER_COLOR = 0x2ECC71
MAX_EMBEDS_PER_MESSAGE = 10
MAX_FIELD_NAME = 256
MAX_DESCRIPTION = 4096
MAX_FIELD_VALUE = 1024
MAX_COMMENTS = 1000
MAX_MESSAGE_CHARS = 6000
MESSAGE_CHAR_BUDGET = 5900  # slack under Discord's 6000-char total across all embeds in a message

MARKDOWN_SPECIALS = re.compile(r"([\\*_~`|>\[\]])")


def escape_markdown(text: str) -> str:
    """Backslash-escape characters Discord would render as markdown."""
    return MARKDOWN_SPECIALS.sub(r"\\\1", text)


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit - 1]
    if (len(head) - len(head.rstrip("\\"))) % 2:
        # An odd run of backslashes would leave a dangling escape before the ellipsis.
        head = head[:-1]
    return head + "…"


def iso_timestamp(epoch: int) -> str | None:
    """Return the epoch as an ISO-8601 UTC string, or None when it is out of range."""
    try:
        return datetime.fromtimestamp(epoch, tz=UTC).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def embed_length(embed: dict) -> int:
    """Characters Discord counts toward the per-message total for one embed."""
    total = len(embed.get("title", "")) + len(embed.get("description", ""))
    for field in embed.get("fields", []):
        total += len(field.get("name", "")) + len(field.get("value", ""))
    total += len(embed.get("footer", {}).get("text", ""))
    total += len(embed.get("author", {}).get("name", ""))
    return total


def group_embeds[T](pairs: list[tuple[dict, list[T]]]) -> list[tuple[list[dict], list[T]]]:
    """Group (embed, items) pairs into messages within Discord's embed-count and character limits."""
    messages: list[tuple[list[dict], list[T]]] = []
    embeds: list[dict] = []
    items: list[T] = []
    size = 0
    for embed, embed_items in pairs:
        length = embed_length(embed)
        full = len(embeds) >= MAX_EMBEDS_PER_MESSAGE or size + length > MESSAGE_CHAR_BUDGET
        if embeds and full:
            messages.append((embeds, items))
            embeds, items, size = [], [], 0
        embeds.append(embed)
        items.extend(embed_items)
        size += length
    if embeds:
        messages.append((embeds, items))
    return messages


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
                "name": truncate(f"{escape_markdown(side['franchise_name'])} gives up", MAX_FIELD_NAME),
                "value": truncate(bullets, MAX_FIELD_VALUE),
                "inline": False,
            }
        )
    embed = {
        "title": "🚨 Trade Completed",
        "color": TRADE_COLOR,
        "fields": fields,
        "footer": footer(league),
    }
    timestamp = iso_timestamp(trade.timestamp)
    if timestamp is not None:
        embed["timestamp"] = timestamp
    if details["comments"]:
        # Trade comments are left unescaped on purpose so members can use markdown in trade notes.
        embed["description"] = truncate(details["comments"], MAX_COMMENTS)
    return embed


# --- waivers ----------------------------------------------------------------


def waiver_details(claim: WaiverClaim, league: LeagueInfo, players: dict[str, Player]) -> dict:
    base = {"franchise_id": claim.franchise, "franchise_name": league.franchise_name(claim.franchise)}
    if not claim.parsed:
        return {
            **base,
            "parsed": claim.parsed,
            "bid": "",
            "added": None,
            "dropped": None,
            "raw_transaction": str(claim.raw.get("transaction", "")),
        }
    return {
        **base,
        "parsed": claim.parsed,
        "bid": format_dollars(claim.bid),
        "added": player_label(players.get(claim.added), claim.added),
        "dropped": player_label(players.get(claim.dropped), claim.dropped) if claim.dropped else None,
    }


def waiver_summary(details: dict) -> str:
    if not details["parsed"]:
        return f"unparsed waiver: {details['franchise_name']} {details['raw_transaction']}"
    text = f"{details['franchise_name']} won {details['added']} for {details['bid']}"
    if details["dropped"]:
        text += f", dropped {details['dropped']}"
    return text


def waiver_line(details: dict) -> str:
    franchise_name = escape_markdown(details["franchise_name"])
    if not details["parsed"]:
        # Inside a code span backslash escapes render literally and a backtick would end the span.
        raw = details["raw_transaction"].replace("`", "'")
        return f"**{franchise_name}** claim could not be parsed: `{raw}`"
    line = f"**{franchise_name}** won **{escape_markdown(details['added'])}** for {details['bid']}"
    if details["dropped"]:
        line += f" · dropped {escape_markdown(details['dropped'])}"
    return line


def chunk_entries[T](entries: list[tuple[T, str]], limit: int) -> list[list[tuple[T, str]]]:
    """Group (item, text) entries so each group's texts joined by newlines fit in limit."""
    chunks: list[list[tuple[T, str]]] = []
    size = 0
    for item, raw_text in entries:
        text = truncate(raw_text, limit)
        needed = len(text) + (1 if chunks else 0)
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
    entries = [(claim, waiver_line(details)) for claim, details in ordered]
    chunks = chunk_entries(entries, MAX_DESCRIPTION)
    timestamp = iso_timestamp(max(claim.timestamp for claim, _ in ordered))
    embed_pairs: list[tuple[dict, list[WaiverClaim]]] = []
    for index, chunk in enumerate(chunks):
        title = "✅ Waiver Claims Processed"
        if len(chunks) > 1:
            title += f" ({index + 1}/{len(chunks)})"
        embed = {
            "title": title,
            "color": WAIVER_COLOR,
            "description": "\n".join(text for _, text in chunk),
            "footer": footer(league),
        }
        if timestamp is not None:
            embed["timestamp"] = timestamp
        embed_pairs.append((embed, [claim for claim, _ in chunk]))
    return group_embeds(embed_pairs)
