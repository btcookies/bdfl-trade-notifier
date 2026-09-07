"""The trade ledger: what each side received and what it went on to produce as starters."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from bdfl.assets import format_dollars
from hof.model.season import DraftPick, Season
from hof.stats.careers import Stint, WeekKey, effective_key
from hof.stats.drafts import original_owner
from hof.stats.league import League
from hof.stats.vor import Start


@dataclass(frozen=True)
class Asset:
    code: str
    kind: str  # player, pick, future_pick, dollars
    label: str
    player_id: str | None  # the player, or the player a pick became
    starts: int  # as a starter for the receiving franchise since the trade
    points: float
    vor: float


@dataclass(frozen=True)
class TradeSide:
    franchise_id: str
    name: str  # at the time
    received: tuple[Asset, ...]
    vor: float


@dataclass(frozen=True)
class TradeLine:
    year: int
    timestamp: int
    effective: WeekKey
    pending: bool  # takes effect after the newest played week, so nothing has been produced yet
    sides: tuple[TradeSide, TradeSide]
    comments: str
    verdict: str


StartIndex = dict[tuple[str, str], list[Start]]  # (player id, franchise id) -> starts


def resolve_future_pick(code: str, league: League, by_name: dict[str, str]) -> tuple[DraftPick, int] | None:
    """FP_<franchise>_<year>_<round> -> (the pick it became, draft year), when exactly one pick matches."""
    parts = code.split("_")
    if len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit():
        return None
    owner, year, round_ = parts[1], int(parts[2]), int(parts[3])
    try:
        season = league.season(year)
    except KeyError:
        return None
    matches = [p for p in season.draft if p.round == round_ and original_owner(p, by_name) == owner]
    return (matches[0], year) if len(matches) == 1 else None


def resolve_current_pick(code: str, season: Season) -> DraftPick | None:
    """DP_<round>_<pick>, both zero-based, -> that pick in the season's draft."""
    parts = code.split("_")
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        return None
    round_, pick = int(parts[1]) + 1, int(parts[2]) + 1
    return next((p for p in season.draft if p.round == round_ and p.pick == pick), None)


def produced(index: StartIndex, stints: list[Stint], player_id: str, franchise_id: str, since: WeekKey) -> tuple[int, float, float]:
    """(starts, points, vor) for the franchise during the player's first stint that reaches `since`."""
    stint = next((s for s in stints if s.franchise_id == franchise_id and s.end >= since), None)
    if stint is None:
        return 0, 0.0, 0.0
    start = max(stint.start, since)
    rows = [r for r in index.get((player_id, franchise_id), []) if start <= (r.year, r.week) <= stint.end]
    return len(rows), round(sum(r.points for r in rows), 1), round(sum(r.vor for r in rows), 1)


def _player_label(league: League, player_id: str) -> str:
    info = league.player_info(player_id)
    return f"{info.name} ({info.position})"


def asset(
    code: str,
    season: Season,
    league: League,
    by_name: dict[str, str],
    index: StartIndex,
    all_stints: dict[str, list[Stint]],
    receiver: str,
    since: WeekKey,
    pending: bool,
) -> Asset:
    def valued(kind: str, label: str, player_id: str | None, from_key: WeekKey) -> Asset:
        if player_id is None or pending:
            return Asset(code, kind, label, player_id, 0, 0.0, 0.0)
        starts, points, vor = produced(index, all_stints.get(player_id, []), player_id, receiver, from_key)
        return Asset(code, kind, label, player_id, starts, points, vor)

    if code.isalnum():
        return valued("player", _player_label(league, code), code, since)
    parts = code.split("_")
    if parts[0] == "BB" and len(parts) == 2:
        return Asset(code, "dollars", f"{format_dollars(parts[1])} blind-bid dollars", None, 0, 0.0, 0.0)
    if parts[0] == "FP" and len(parts) == 4:
        label = f"{league.name_in(parts[1], season.year)} {parts[2]} Round {parts[3]} pick"
        resolved = resolve_future_pick(code, league, by_name)
        if resolved is None:
            return Asset(code, "future_pick", label, None, 0, 0.0, 0.0)
        pick, year = resolved
        return valued("future_pick", f"{label} → {league.player_info(pick.player_id).name}", pick.player_id, (year, 0))
    if parts[0] == "DP" and len(parts) == 3:
        pick = resolve_current_pick(code, season)
        label = f"{season.year} Round {parts[1]} Pick {parts[2]}"
        if pick is not None:
            label = f"{season.year} Round {pick.round} Pick {pick.pick} → {league.player_info(pick.player_id).name}"
            return valued("pick", label, pick.player_id, (season.year, 0))
        return Asset(code, "pick", label, None, 0, 0.0, 0.0)
    return Asset(code, "other", code, None, 0, 0.0, 0.0)


def verdict(first: TradeSide, second: TradeSide, pending: bool) -> str:
    if pending:
        return "Pending"
    diff = round(first.vor - second.vor, 1)
    if abs(diff) < 0.05:
        return "Even"
    ahead = first if diff > 0 else second
    return f"Ahead: {ahead.name} by {abs(diff):.1f}"


def trade_ledger(league: League, all_stints: dict[str, list[Stint]]) -> list[TradeLine]:
    """Every trade in every season, newest first."""
    by_name = league.franchise_by_name()
    index: StartIndex = defaultdict(list)
    for row in league.all_starts():
        index[(row.player_id, row.franchise_id)].append(row)
    played = [(season.year, game.week) for season in league.seasons for game in season.games()]
    newest = max(played) if played else (0, 0)  # rosters can exist before kickoff; only played weeks settle a trade
    lines: list[TradeLine] = []
    for season in league.seasons:
        for trade in season.transactions.trades:
            since = effective_key(season, trade.timestamp)
            pending = since > newest
            sides = []
            for receiver, codes in ((trade.franchise1, trade.gave_up2), (trade.franchise2, trade.gave_up1)):
                received = tuple(asset(code, season, league, by_name, index, all_stints, receiver, since, pending) for code in codes)
                sides.append(TradeSide(receiver, league.name_in(receiver, season.year), received, round(sum(a.vor for a in received), 1)))
            first, second = sides
            lines.append(TradeLine(season.year, trade.timestamp, since, pending, (first, second), trade.comments, verdict(first, second, pending)))
    return sorted(lines, key=lambda line: (-line.year, -line.timestamp))
