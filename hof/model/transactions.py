"""Typed view of one season's MFL transaction log."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from bdfl.models import WAIVER_RE, as_list, split_assets

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Trade:
    timestamp: int
    franchise1: str
    franchise2: str
    gave_up1: tuple[str, ...]  # asset codes franchise1 sent to franchise2
    gave_up2: tuple[str, ...]
    comments: str


@dataclass(frozen=True)
class WaiverClaim:
    timestamp: int
    franchise: str
    added: str
    bid: str
    dropped: str | None


@dataclass(frozen=True)
class FreeAgentMove:
    timestamp: int
    franchise: str
    added: tuple[str, ...]
    dropped: tuple[str, ...]


@dataclass(frozen=True)
class RosterMove:
    """An IR or taxi-squad move: `on` went onto the squad, `off` came off it."""

    timestamp: int
    franchise: str
    kind: str  # "IR" or "TAXI"
    on: tuple[str, ...]
    off: tuple[str, ...]


@dataclass(frozen=True)
class TransactionLog:
    trades: tuple[Trade, ...]
    waivers: tuple[WaiverClaim, ...]
    free_agents: tuple[FreeAgentMove, ...]
    roster_moves: tuple[RosterMove, ...]
    lock_times: tuple[int, ...]  # LOCK_ALL_PLAYERS timestamps ascending; the k-th is week start_week + k - 1

    def week_locked_at(self, week: int, start_week: int) -> int | None:
        index = week - start_week
        if 0 <= index < len(self.lock_times):
            return self.lock_times[index]
        return None

    def effective_week(self, timestamp: int, start_week: int) -> int | None:
        """First week whose lock is after the timestamp; None once the season's last lock has passed."""
        for index, lock in enumerate(self.lock_times):
            if lock > timestamp:
                return start_week + index
        return None


def parse_transactions(body: dict[str, Any]) -> TransactionLog:
    trades: list[Trade] = []
    waivers: list[WaiverClaim] = []
    free_agents: list[FreeAgentMove] = []
    moves: list[RosterMove] = []
    locks: list[int] = []
    for raw in as_list((body.get("transactions") or {}).get("transaction")):
        kind = raw.get("type")
        try:
            timestamp = int(raw["timestamp"])
            if kind == "TRADE":
                trades.append(
                    Trade(
                        timestamp=timestamp,
                        franchise1=raw["franchise"],
                        franchise2=raw["franchise2"],
                        gave_up1=split_assets(raw.get("franchise1_gave_up")),
                        gave_up2=split_assets(raw.get("franchise2_gave_up")),
                        comments=(raw.get("comments") or "").strip(),
                    )
                )
            elif kind == "BBID_WAIVER":
                match = WAIVER_RE.fullmatch(str(raw.get("transaction") or ""))
                if match is None:
                    log.warning("unparsable waiver %r", raw.get("transaction"))
                    continue
                waivers.append(
                    WaiverClaim(timestamp, raw["franchise"], match.group(1), match.group(2), match.group(3) or None)
                )
            elif kind == "FREE_AGENT":
                added, _, dropped = str(raw.get("transaction") or "").partition("|")
                free_agents.append(
                    FreeAgentMove(timestamp, raw["franchise"], split_assets(added), split_assets(dropped))
                )
            elif kind == "IR":
                moves.append(
                    RosterMove(timestamp, raw["franchise"], "IR", split_assets(raw.get("deactivated")), split_assets(raw.get("activated")))
                )
            elif kind == "TAXI":
                moves.append(
                    RosterMove(timestamp, raw["franchise"], "TAXI", split_assets(raw.get("demoted")), split_assets(raw.get("promoted")))
                )
            elif kind == "LOCK_ALL_PLAYERS":
                locks.append(timestamp)
        except (KeyError, ValueError, TypeError) as exc:
            log.warning("skipping unparsable %s transaction %r", kind, raw, exc_info=exc)

    def by_time(entry):
        return entry.timestamp

    return TransactionLog(
        trades=tuple(sorted(trades, key=by_time)),
        waivers=tuple(sorted(waivers, key=by_time)),
        free_agents=tuple(sorted(free_agents, key=by_time)),
        roster_moves=tuple(sorted(moves, key=by_time)),
        lock_times=tuple(sorted(locks)),
    )
