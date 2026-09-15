"""Weekly awards: nine superlatives over a week's counted games.

Ties break on the holder's score that week (higher first), then on the holder's name, so the
output is deterministic. An award with no candidate is omitted.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from hof.model.season import Game, Lineup, Season
from hof.stats import allplay
from hof.stats.league import League

AWARD_KEYS = (
    "high_score",
    "low_score",
    "blowout",
    "closest",
    "best_lineup",
    "worst_lineup",
    "lucky_win",
    "unlucky_loss",
    "best_benched",
)
DEFAULT_LABELS = {
    "high_score": "Highest score",
    "low_score": "Lowest score",
    "blowout": "Biggest blowout",
    "closest": "Closest game",
    "best_lineup": "Best lineup",
    "worst_lineup": "Most points left on the bench",
    "lucky_win": "Luckiest win",
    "unlucky_loss": "Unluckiest loss",
    "best_benched": "Best player on a bench",
}


@dataclass(frozen=True)
class Award:
    key: str
    label: str
    holder_id: str  # franchise id, or the player id for best_benched
    holder_name: str
    franchise_id: str  # the franchise credited in the tally
    value: float
    unit: str  # pts, pct, or wins
    detail: str  # one line; empty when there is nothing to add


def format_value(value: float, unit: str) -> str:
    if unit == "pct":
        return f"{value * 100:.1f}%"
    if unit == "wins":
        return f"{value:+.1f}"
    return f"{value:.1f}"


def labels_with(overrides: dict[str, str] | None) -> dict[str, str]:
    return {**DEFAULT_LABELS, **(overrides or {})}


def _score(value: float | None) -> str:
    return f"{value or 0.0:.1f}"


def _versus(own: Lineup, other: Lineup, other_name: str) -> str:
    own_score, other_score = own.score or 0.0, other.score or 0.0
    verb = "beat" if own_score > other_score else "lost to" if own_score < other_score else "tied"
    return f"{verb} {other_name} {_score(own_score)}–{_score(other_score)}"


def _entries(season: Season, week: int) -> list[tuple[Game, Lineup, Lineup]]:
    """(game, own lineup, opponent lineup) for both sides of every counted game in the week."""
    out: list[tuple[Game, Lineup, Lineup]] = []
    for game in season.games():
        if game.week == week:
            out.append((game, game.home, game.away))
            out.append((game, game.away, game.home))
    return out


def week_awards(league: League, season: Season, week: int, labels: dict[str, str] | None = None) -> list[Award]:
    """Every award with a candidate, in AWARD_KEYS order."""
    names = labels_with(labels)
    entries = _entries(season, week)
    if not entries:
        return []
    year = season.year
    franchise_name = {lineup.franchise_id: league.name_in(lineup.franchise_id, year) for _, lineup, _ in entries}
    playoff = week > season.last_regular_season_week
    allplay_record = {row.franchise_id: row.record for row in ([] if playoff else allplay.all_play_week(season, week))}

    def franchise(key: str, own: Lineup, value: float, unit: str, detail: str) -> Award:
        fid = own.franchise_id
        return Award(key, names[key], fid, franchise_name[fid], fid, value, unit, detail)

    def best(candidates: list[tuple[float, Lineup, str]], lowest: bool = False) -> tuple[float, Lineup, str] | None:
        """(value, lineup, detail) with the extreme value; ties go to the higher score, then name."""
        if not candidates:
            return None
        sign = 1 if lowest else -1
        return min(candidates, key=lambda c: (sign * c[0], -(c[1].score or 0.0), franchise_name[c[1].franchise_id]))

    found: list[Award] = []

    scores = [(own.score or 0.0, own, _versus(own, other, franchise_name[other.franchise_id])) for _, own, other in entries]
    if (pick := best(scores)) is not None:
        found.append(franchise("high_score", pick[1], round(pick[0], 1), "pts", pick[2]))
    if (pick := best(scores, lowest=True)) is not None:
        found.append(franchise("low_score", pick[1], round(pick[0], 1), "pts", pick[2]))

    margins: list[tuple[float, Lineup, str]] = []
    for game, own, _other in entries:
        if own is game.home:  # one candidate per game, from the winner's side (home on a tie)
            winner = game.winner or game.home
            loser = game.loser or game.away
            if game.tie:
                detail = f"tied with {franchise_name[loser.franchise_id]}, {_score(winner.score)}–{_score(loser.score)}"
            else:
                detail = f"over {franchise_name[loser.franchise_id]}, {_score(winner.score)}–{_score(loser.score)}"
            margins.append((game.margin, winner, detail))
    if (pick := best(margins)) is not None:
        found.append(franchise("blowout", pick[1], pick[0], "pts", pick[2]))
    if (pick := best(margins, lowest=True)) is not None:
        found.append(franchise("closest", pick[1], pick[0], "pts", pick[2]))

    # A lineup cannot be rated when its optimal is None (not computed), 0.0 (nothing could have
    # scored; it would also divide by zero below), or below the actual score (an MFL data glitch
    # that would read as more than 100% efficiency).
    lineups = [(own, own.opt_pts) for _, own, _ in entries if own.opt_pts and own.opt_pts >= (own.score or 0.0)]
    efficiency = [((own.score or 0.0) / opt, own, f"{_score(own.score)} of {_score(opt)} possible") for own, opt in lineups]
    if (pick := best(efficiency)) is not None:
        found.append(franchise("best_lineup", pick[1], round(pick[0], 3), "pct", pick[2]))
    left = [(round(opt - (own.score or 0.0), 1), own, f"{_score(own.score)} of {_score(opt)} possible") for own, opt in lineups]
    if (pick := best(left)) is not None:
        found.append(franchise("worst_lineup", pick[1], pick[0], "pts", pick[2]))

    def field_detail(own: Lineup) -> str:
        record = allplay_record.get(own.franchise_id)
        return f"would have gone {record} against the field" if record else ""

    winners = [(own.score or 0.0, own, field_detail(own)) for game, own, _ in entries if game.winner is own]
    if (pick := best(winners, lowest=True)) is not None:
        found.append(franchise("lucky_win", pick[1], round(pick[0], 1), "pts", pick[2]))
    losers = [(own.score or 0.0, own, field_detail(own)) for game, own, _ in entries if game.loser is own]
    if (pick := best(losers)) is not None:
        found.append(franchise("unlucky_loss", pick[1], round(pick[0], 1), "pts", pick[2]))

    benched: list[tuple[float, str, Lineup]] = [
        (own.points(pid), pid, own) for _, own, _ in entries for pid in own.nonstarters if pid in own.scores
    ]
    if benched:
        points, pid, own = min(benched, key=lambda b: (-b[0], season.player(b[1]).name, b[1]))
        fid = own.franchise_id
        found.append(
            Award("best_benched", names["best_benched"], pid, season.player(pid).name, fid, round(points, 1), "pts", f"on {franchise_name[fid]}'s bench")
        )

    order = {key: i for i, key in enumerate(AWARD_KEYS)}
    return sorted(found, key=lambda a: order[a.key])


def tally(weeks: Iterable[Iterable[Award]], franchise_ids: Iterable[str]) -> dict[str, dict[str, int]]:
    """franchise id -> award key -> count, with every franchise and key present."""
    counts = {fid: dict.fromkeys(AWARD_KEYS, 0) for fid in franchise_ids}
    for week in weeks:
        for award in week:
            counts.setdefault(award.franchise_id, dict.fromkeys(AWARD_KEYS, 0))[award.key] += 1
    return counts


def leaders(counts: dict[str, dict[str, int]]) -> tuple[tuple[str, ...], int]:
    """(franchise ids sharing the most awards of any kind, that count); ((), 0) when nobody has one."""
    totals = {fid: sum(keyed.values()) for fid, keyed in counts.items()}
    most = max(totals.values(), default=0)
    if most == 0:
        return (), 0
    return tuple(sorted(fid for fid, total in totals.items() if total == most)), most
