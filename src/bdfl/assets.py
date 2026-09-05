"""Render MFL asset codes and players as human-readable text."""

from __future__ import annotations

import logging

from bdfl.models import LeagueInfo, Player

log = logging.getLogger(__name__)


def format_player_name(name: str) -> str:
    """MFL gives 'Last, First'; return 'First Last'."""
    if "," in name:
        last, first = name.split(",", 1)
        return f"{first.strip()} {last.strip()}".strip()
    return name.strip()


def player_label(player: Player | None, player_id: str) -> str:
    """Return 'First Last, TEAM POS', or an 'Unknown player' marker when the player is missing."""
    name = format_player_name(player.name) if player is not None else ""
    if not name:
        return f"Unknown player (#{player_id})"
    tag = " ".join(part for part in (player.team, player.position) if part)
    return f"{name}, {tag}" if tag else name


def format_dollars(amount: str) -> str:
    """Return amount formatted as a dollar string, falling back to the raw input if it isn't a finite number."""
    try:
        value = float(amount)
        return f"${int(value)}" if value == int(value) else f"${value:.2f}"
    except (ValueError, OverflowError):
        return f"${amount}"


def render_asset(code: str, league: LeagueInfo, players: dict[str, Player]) -> str:
    """Return a human-readable label for an asset code, falling back to the raw code if unrecognized."""
    if code.isdigit():
        return player_label(players.get(code), code)
    parts = code.split("_")
    if parts[0] == "BB" and len(parts) == 2:
        return f"{format_dollars(parts[1])} blind bid dollars"
    if parts[0] == "FP" and len(parts) == 4 and parts[1] and parts[2].isdecimal() and parts[3].isdecimal():
        _, franchise_id, year, rnd = parts
        return f"{league.franchise_name(franchise_id)} {year} Round {int(rnd)} pick"
    if parts[0] == "DP" and len(parts) == 3 and parts[1].isdecimal() and parts[2].isdecimal():
        # MFL encodes current-year picks zero-based: DP_2_5 is round 3, pick 6.
        return f"{league.year} Round {int(parts[1]) + 1} Pick {int(parts[2]) + 1}"
    log.warning("unknown asset code %s", code)
    return code.strip() or "(empty asset)"
