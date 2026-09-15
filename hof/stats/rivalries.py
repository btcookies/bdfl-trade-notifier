"""The all-time rivalry grid and the pairs worth talking about."""

from __future__ import annotations

from dataclasses import dataclass

from hof.stats.franchises import FranchiseHistory

MIN_MEETINGS = 5
LIST_SIZE = 5


@dataclass(frozen=True)
class Pair:
    """One unordered pair of franchises, by current names; a is the lower franchise id."""

    a_id: str
    a_name: str
    b_id: str
    b_name: str
    a_wins: int
    b_wins: int
    ties: int

    @property
    def meetings(self) -> int:
        return self.a_wins + self.b_wins + self.ties

    @property
    def gap(self) -> float:
        """Distance of a's win share from .500; 0 is dead even."""
        return abs((self.a_wins + 0.5 * self.ties) / self.meetings - 0.5) if self.meetings else 0.0

    @property
    def record(self) -> str:
        """From a's side, with ties only when there are any."""
        text = f"{self.a_wins}-{self.b_wins}"
        return f"{text}-{self.ties}" if self.ties else text

    @property
    def leader_line(self) -> str:
        if self.a_wins == self.b_wins:
            return f"{self.a_name} and {self.b_name} are even at {self.record}"
        if self.a_wins > self.b_wins:
            return f"{self.a_name} leads {self.b_name} {self.record}"
        flipped = f"{self.b_wins}-{self.a_wins}" + (f"-{self.ties}" if self.ties else "")
        return f"{self.b_name} leads {self.a_name} {flipped}"


@dataclass(frozen=True)
class RivalryGrid:
    order: tuple[str, ...]  # franchise ids in the franchises index order
    cells: dict[tuple[str, str], tuple[int, int, int]]  # (row id, column id) -> row's W, L, T
    most_played: tuple[Pair, ...]
    most_lopsided: tuple[Pair, ...]
    most_even: tuple[Pair, ...]


def ranked(histories: dict[str, FranchiseHistory]) -> list[FranchiseHistory]:
    """The franchises index order: all-time win percentage, then points for, then name."""
    return sorted(histories.values(), key=lambda h: (-h.totals.win_pct, -h.totals.points_for, h.name))


def rivalry_grid(histories: dict[str, FranchiseHistory], min_meetings: int = MIN_MEETINGS) -> RivalryGrid:
    cells: dict[tuple[str, str], tuple[int, int, int]] = {}
    pairs: list[Pair] = []
    for history in histories.values():
        for series in history.series:
            cells[(history.id, series.opponent_id)] = (series.wins, series.losses, series.ties)
            if history.id < series.opponent_id:
                pairs.append(Pair(history.id, history.name, series.opponent_id, series.opponent_name, series.wins, series.losses, series.ties))

    def names(pair: Pair) -> tuple[str, str]:
        return (pair.a_name.casefold(), pair.b_name.casefold())

    most_played = sorted(pairs, key=lambda p: (-p.meetings, names(p)))[:LIST_SIZE]
    eligible = [p for p in pairs if p.meetings >= min_meetings]
    most_lopsided = sorted(eligible, key=lambda p: (-p.gap, -p.meetings, names(p)))[:LIST_SIZE]
    most_even = sorted(eligible, key=lambda p: (p.gap, -p.meetings, names(p)))[:LIST_SIZE]
    return RivalryGrid(
        order=tuple(h.id for h in ranked(histories)),
        cells=cells,
        most_played=tuple(most_played),
        most_lopsided=tuple(most_lopsided),
        most_even=tuple(most_even),
    )
