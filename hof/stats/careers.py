"""Player careers: roster stints, per-season lines, and how each stint began and ended."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from bdfl.assets import format_dollars
from hof.model.season import Season
from hof.stats.league import League

WeekKey = tuple[int, int]  # (year, week); (year, 0) means "before week 1 of year"


@dataclass(frozen=True)
class Stint:
    player_id: str
    franchise_id: str
    start: WeekKey  # first rostered week
    end: WeekKey  # last rostered week


@dataclass(frozen=True)
class Move:
    kind: str  # drafted, traded, claimed, signed, joined, traded away, dropped, left
    year: int
    week: int
    franchise_id: str
    detail: str = ""


@dataclass(frozen=True)
class SeasonLine:
    year: int
    franchise_ids: tuple[str, ...]  # every franchise rostering the player that season, first seen first
    starts: int
    points: float
    vor: float
    bench_points: float
    playoff_starts: int
    playoff_points: float
    title: bool  # started for the champion in the final


@dataclass(frozen=True)
class Career:
    player_id: str
    name: str
    position: str
    first_year: int
    last_year: int
    active: bool  # on a roster in the newest rostered week
    seasons: tuple[SeasonLine, ...]
    stints: tuple[Stint, ...]
    moves: tuple[Move, ...]
    starts: int
    points: float
    vor: float
    bench_points: float
    playoff_starts: int
    playoff_points: float
    titles: int
    franchise_ids: tuple[str, ...]  # in order of first stint


@dataclass(frozen=True)
class Transfer:
    """A transaction that put a player on (adding) or took one off (removing) a franchise."""

    key: WeekKey
    kind: str
    franchise_id: str
    detail: str


def effective_key(season: Season, timestamp: int) -> WeekKey:
    """The (year, week) a transaction takes effect.

    Before a season's first weekly lock fires (the whole offseason, and the days before week 1)
    the log has no lock times at all, and every transaction takes effect in the first week.
    Once the last lock has passed, a transaction rolls into the next season as (year + 1, 0).
    """
    if not season.transactions.lock_times:
        return (season.year, season.start_week)
    week = season.transactions.effective_week(timestamp, season.start_week)
    return (season.year, week) if week is not None else (season.year + 1, 0)


Rosters = dict[int, dict[int, dict[str, set[str]]]]  # year -> week -> player id -> franchises


def rosters_by_year(league: League) -> Rosters:
    """Computed once per run because League.rosters() rebuilds its answer on every call."""
    return {season.year: league.rosters(season.year) for season in league.seasons}


def following_weeks(rosters: Rosters) -> dict[WeekKey, WeekKey]:
    """Each rostered (year, week) -> the next rostered one; the newest week has no entry."""
    keys = [(year, week) for year in sorted(rosters) for week in sorted(rosters[year])]
    return dict(zip(keys, keys[1:], strict=False))


def stints(league: League, rosters: Rosters | None = None) -> dict[str, list[Stint]]:
    """Runs of consecutive rostered weeks per player and franchise; the offseason does not break a run."""
    rosters = rosters if rosters is not None else rosters_by_year(league)
    open_: dict[tuple[str, str], Stint] = {}
    done: dict[str, list[Stint]] = defaultdict(list)
    for season in league.seasons:
        weeks = rosters[season.year]
        for week in sorted(weeks):
            current = {(pid, fid) for pid, fids in weeks[week].items() for fid in fids}
            for key in list(open_):
                if key not in current:
                    done[key[0]].append(open_.pop(key))
            for pid, fid in current:
                previous = open_.get((pid, fid))
                start = previous.start if previous else (season.year, week)
                open_[(pid, fid)] = Stint(pid, fid, start, (season.year, week))
    for (pid, _), stint in open_.items():
        done[pid].append(stint)
    return {pid: sorted(rows, key=lambda s: s.start) for pid, rows in done.items()}


def transfers(league: League) -> tuple[dict[str, list[Transfer]], dict[str, list[Transfer]]]:
    """(adding, removing) transfers per player id, from every season's transaction log."""
    adding: dict[str, list[Transfer]] = defaultdict(list)
    removing: dict[str, list[Transfer]] = defaultdict(list)
    for season in league.seasons:
        log = season.transactions
        for trade in log.trades:
            key = effective_key(season, trade.timestamp)
            name1, name2 = season.franchise_name(trade.franchise1), season.franchise_name(trade.franchise2)
            for pid in trade.gave_up1:
                if pid.isalnum():
                    removing[pid].append(Transfer(key, "traded away", trade.franchise1, f"to {name2}"))
                    adding[pid].append(Transfer(key, "traded", trade.franchise2, f"from {name1}"))
            for pid in trade.gave_up2:
                if pid.isalnum():
                    removing[pid].append(Transfer(key, "traded away", trade.franchise2, f"to {name1}"))
                    adding[pid].append(Transfer(key, "traded", trade.franchise1, f"from {name2}"))
        for claim in log.waivers:
            key = effective_key(season, claim.timestamp)
            adding[claim.added].append(Transfer(key, "claimed", claim.franchise, format_dollars(claim.bid)))
            if claim.dropped:
                removing[claim.dropped].append(Transfer(key, "dropped", claim.franchise, ""))
        for move in log.free_agents:
            key = effective_key(season, move.timestamp)
            for pid in move.added:
                adding[pid].append(Transfer(key, "signed", move.franchise, ""))
            for pid in move.dropped:
                removing[pid].append(Transfer(key, "dropped", move.franchise, ""))
    return adding, removing


def bridge_gaps(all_stints: dict[str, list[Stint]], removing: dict[str, list[Transfer]]) -> dict[str, list[Stint]]:
    """Join consecutive stints on one franchise when nothing moved the player off it in between.

    MFL's weekly lineups omit players on injured reserve and the taxi squad, so a player who
    spent weeks on IR looks like they left and came back. The transaction log says otherwise:
    only a drop or a trade away inside the gap means the player really left.
    """
    bridged: dict[str, list[Stint]] = {}
    for pid, rows in all_stints.items():
        merged: list[Stint] = []
        for stint in rows:
            last = merged[-1] if merged else None
            gap_moves = [
                t for t in removing.get(pid, [])
                if last is not None and t.franchise_id == stint.franchise_id and last.end < t.key <= stint.start
            ]
            if last is not None and last.franchise_id == stint.franchise_id and last.end < stint.start and not gap_moves:
                merged[-1] = Stint(pid, stint.franchise_id, last.start, stint.end)
            else:
                merged.append(stint)
        bridged[pid] = merged
    return bridged


def roster_stints(league: League, rosters: Rosters | None = None) -> dict[str, list[Stint]]:
    """Stints with IR and taxi gaps bridged; what careers and the trade ledger should use."""
    _, removing = transfers(league)
    return bridge_gaps(stints(league, rosters), removing)


def _drafted(league: League, stint: Stint) -> Move | None:
    season = league.season(stint.start[0])
    for pick in season.draft:
        if pick.player_id == stint.player_id and pick.franchise_id == stint.franchise_id:
            return Move("drafted", season.year, stint.start[1], stint.franchise_id, f"Round {pick.round}, Pick {pick.pick}")
    return None


def moves_for(
    league: League,
    player_stints: list[Stint],
    adding: list[Transfer],
    removing: list[Transfer],
    following: dict[WeekKey, WeekKey],
) -> tuple[Move, ...]:
    moves: list[Move] = []
    previous_end: dict[str, WeekKey] = {}
    for stint in player_stints:
        floor = previous_end.get(stint.franchise_id, (0, 0))
        arrivals = [t for t in adding if t.franchise_id == stint.franchise_id and floor < t.key <= stint.start]
        drafted = _drafted(league, stint) if stint.franchise_id not in previous_end else None
        if arrivals:
            latest = max(arrivals, key=lambda t: t.key)
            moves.append(Move(latest.kind, stint.start[0], stint.start[1], stint.franchise_id, latest.detail))
        elif drafted is not None:
            moves.append(drafted)
        else:
            moves.append(Move("joined", stint.start[0], stint.start[1], stint.franchise_id))
        after = following.get(stint.end)
        if after is not None:
            departures = [t for t in removing if t.franchise_id == stint.franchise_id and stint.end < t.key <= after]
            if departures:
                first = min(departures, key=lambda t: t.key)
                moves.append(Move(first.kind, stint.end[0], stint.end[1], stint.franchise_id, first.detail))
            else:
                moves.append(Move("left", stint.end[0], stint.end[1], stint.franchise_id))
        previous_end[stint.franchise_id] = stint.end
    return tuple(moves)


def bench_points(season: Season) -> dict[str, float]:
    """Player id -> points scored on the bench in counted games this season."""
    totals: dict[str, float] = defaultdict(float)
    for game in season.games():
        for lineup in (game.home, game.away):
            for pid in lineup.nonstarters:
                totals[pid] += lineup.points(pid)
    return {pid: round(v, 1) for pid, v in totals.items()}


def title_starters(season: Season) -> set[str]:
    final = season.final
    if final is None or final.winner is None:
        return set()
    return set(final.winner.starters)


def careers(league: League, all_stints: dict[str, list[Stint]] | None = None) -> dict[str, Career]:
    """Every player with at least one counted start, keyed by player id.

    Pass the result of roster_stints() when the caller also needs it, to compute it once.
    """
    rosters = rosters_by_year(league)
    following = following_weeks(rosters)
    adding, removing = transfers(league)
    if all_stints is None:
        all_stints = bridge_gaps(stints(league, rosters), removing)
    newest = league.latest_rostered_week()
    by_player_year: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    for row in league.all_starts():
        by_player_year[row.player_id][row.year].append(row)
    bench_by_year = {s.year: bench_points(s) for s in league.seasons}
    titles_by_year = {s.year: title_starters(s) for s in league.seasons}
    rostered_by_year: dict[int, dict[str, list[str]]] = {}
    for season in league.seasons:
        seen: dict[str, list[str]] = defaultdict(list)
        for week in sorted(rosters[season.year]):
            for pid, fids in rosters[season.year][week].items():
                for fid in sorted(fids):
                    if fid not in seen[pid]:
                        seen[pid].append(fid)
        rostered_by_year[season.year] = seen

    result: dict[str, Career] = {}
    for pid, by_year in by_player_year.items():
        lines: list[SeasonLine] = []
        for season in league.seasons:
            rows = by_year.get(season.year, [])
            rostered = rostered_by_year[season.year].get(pid, [])
            if not rows and not rostered:
                continue
            lines.append(
                SeasonLine(
                    year=season.year,
                    franchise_ids=tuple(rostered),
                    starts=len(rows),
                    points=round(sum(r.points for r in rows), 1),
                    vor=round(sum(r.vor for r in rows), 1),
                    bench_points=bench_by_year[season.year].get(pid, 0.0),
                    playoff_starts=sum(1 for r in rows if r.playoff),
                    playoff_points=round(sum(r.points for r in rows if r.playoff), 1),
                    title=pid in titles_by_year[season.year],
                )
            )
        player_stints = all_stints.get(pid, [])
        info = league.player_info(pid)
        franchise_order: list[str] = []
        for stint in player_stints:
            if stint.franchise_id not in franchise_order:
                franchise_order.append(stint.franchise_id)
        result[pid] = Career(
            player_id=pid,
            name=info.name,
            position=info.position,
            first_year=lines[0].year,
            last_year=lines[-1].year,
            active=bool(player_stints) and newest is not None and player_stints[-1].end == newest,
            seasons=tuple(lines),
            stints=tuple(player_stints),
            moves=moves_for(league, player_stints, adding.get(pid, []), removing.get(pid, []), following),
            starts=sum(line.starts for line in lines),
            points=round(sum(line.points for line in lines), 1),
            vor=round(sum(line.vor for line in lines), 1),
            bench_points=round(sum(line.bench_points for line in lines), 1),
            playoff_starts=sum(line.playoff_starts for line in lines),
            playoff_points=round(sum(line.playoff_points for line in lines), 1),
            titles=sum(1 for line in lines if line.title),
            franchise_ids=tuple(franchise_order),
        )
    return result
