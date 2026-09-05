"""Data types for league info, players, and MFL transactions."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

WAIVER_RE = re.compile(r"(\d+),\|([\d.]+)\|(\d*),?")


def as_list(value: Any) -> list:
    """MFL returns a dict instead of a one-element list; normalize to a list."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def split_assets(value: str | None) -> tuple[str, ...]:
    return tuple(code for code in (value or "").split(",") if code)


@dataclass(frozen=True)
class LeagueInfo:
    year: int
    name: str
    franchises: dict[str, str] = field(default_factory=dict)

    def franchise_name(self, franchise_id: str) -> str:
        return self.franchises.get(franchise_id, f"Franchise {franchise_id}")


@dataclass(frozen=True)
class Player:
    id: str
    name: str
    team: str = ""
    position: str = ""


@dataclass(frozen=True)
class Trade:
    timestamp: int
    franchise1: str
    franchise2: str
    gave_up1: tuple[str, ...]
    gave_up2: tuple[str, ...]
    comments: str
    raw: dict

    type = "TRADE"

    @property
    def key(self) -> str:
        return f"TRADE#{self.timestamp}#{self.franchise1}#{self.franchise2}"

    @property
    def franchise_ids(self) -> list[str]:
        return [self.franchise1, self.franchise2]


@dataclass(frozen=True)
class WaiverClaim:
    timestamp: int
    franchise: str
    added: str
    bid: str
    dropped: str | None
    parsed: bool
    raw: dict

    type = "BBID_WAIVER"

    @property
    def key(self) -> str:
        if self.parsed:
            return f"WAIVER#{self.timestamp}#{self.franchise}#{self.added}"
        digest = hashlib.sha1(str(self.raw.get("transaction", "")).encode()).hexdigest()[:8]
        return f"WAIVER#{self.timestamp}#{self.franchise}#unparsed-{digest}"

    @property
    def franchise_ids(self) -> list[str]:
        return [self.franchise]


Record = Trade | WaiverClaim


def parse_transactions(payload: dict) -> list[Record]:
    raw_list = as_list((payload.get("transactions") or {}).get("transaction"))
    records: list[Record] = []
    for raw in raw_list:
        kind = raw.get("type")
        if kind == "TRADE":
            records.append(_parse_trade(raw))
        elif kind == "BBID_WAIVER":
            records.append(_parse_waiver(raw))
    return records


def _parse_trade(raw: dict) -> Trade:
    return Trade(
        timestamp=int(raw["timestamp"]),
        franchise1=raw["franchise"],
        franchise2=raw["franchise2"],
        gave_up1=split_assets(raw.get("franchise1_gave_up")),
        gave_up2=split_assets(raw.get("franchise2_gave_up")),
        comments=(raw.get("comments") or "").strip(),
        raw=raw,
    )


def _parse_waiver(raw: dict) -> WaiverClaim:
    timestamp = int(raw["timestamp"])
    franchise = raw["franchise"]
    match = WAIVER_RE.fullmatch(raw.get("transaction") or "")
    if not match:
        return WaiverClaim(timestamp, franchise, "", "", None, False, raw)
    return WaiverClaim(
        timestamp=timestamp,
        franchise=franchise,
        added=match.group(1),
        bid=match.group(2),
        dropped=match.group(3) or None,
        parsed=True,
        raw=raw,
    )


def referenced_player_ids(records: list[Record]) -> set[str]:
    ids: set[str] = set()
    for record in records:
        if isinstance(record, Trade):
            ids.update(code for code in record.gave_up1 + record.gave_up2 if code.isdigit())
        elif record.parsed:
            ids.add(record.added)
            if record.dropped:
                ids.add(record.dropped)
    return ids
