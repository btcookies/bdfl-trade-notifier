"""Player identity for one season, from that season's players snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bdfl.assets import format_player_name
from bdfl.models import as_list

UNKNOWN_POSITION = "UNK"


@dataclass(frozen=True)
class PlayerInfo:
    id: str
    name: str
    position: str
    team: str

    @classmethod
    def unknown(cls, player_id: str) -> PlayerInfo:
        return cls(id=player_id, name=f"Unknown player (#{player_id})", position=UNKNOWN_POSITION, team="")


def parse_players(body: dict[str, Any]) -> dict[str, PlayerInfo]:
    """Player id to PlayerInfo; MFL's 'Last, First' becomes 'First Last'."""
    players: dict[str, PlayerInfo] = {}
    for raw in as_list((body.get("players") or {}).get("player")):
        if "id" not in raw:
            continue
        player_id = str(raw["id"]).strip()
        name = format_player_name(str(raw.get("name") or ""))
        players[player_id] = PlayerInfo(
            id=player_id,
            name=name or f"Unknown player (#{player_id})",
            position=str(raw.get("position") or UNKNOWN_POSITION).strip(),
            team=str(raw.get("team") or "").strip(),
        )
    return players
