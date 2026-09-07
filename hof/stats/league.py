"""The whole league: every season plus its Start rows, and the cross-season lookups."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from hof.model.players import PlayerInfo
from hof.model.season import Season, normalize_name
from hof.stats.vor import Start, starts


@dataclass(frozen=True)
class Era:
    """A run of consecutive seasons in which a franchise kept one name (ignoring cosmetics)."""

    franchise_id: str
    name: str  # the newest spelling used in the era
    first_year: int
    last_year: int


@dataclass
class League:
    seasons: list[Season]  # ascending by year
    starts: dict[int, list[Start]] = field(default_factory=dict)  # year -> starts

    @classmethod
    def build(cls, seasons: list[Season]) -> League:
        ordered = sorted(seasons, key=lambda s: s.year)
        return cls(ordered, {s.year: starts(s) for s in ordered})

    # --- seasons -------------------------------------------------------------

    @property
    def latest(self) -> Season:
        return self.seasons[-1]

    def season(self, year: int) -> Season:
        for season in self.seasons:
            if season.year == year:
                return season
        raise KeyError(year)

    def completed(self) -> list[Season]:
        return [s for s in self.seasons if s.complete]

    def all_starts(self) -> list[Start]:
        return [row for season in self.seasons for row in self.starts[season.year]]

    # --- franchises ----------------------------------------------------------

    def franchise_ids(self) -> list[str]:
        return sorted({fid for s in self.seasons for fid in s.franchises})

    def name_in(self, franchise_id: str, year: int) -> str:
        """The name the franchise used in that season, or its current name when it did not exist."""
        season = self.season(year)
        franchise = season.franchises.get(franchise_id)
        return franchise.name if franchise else self.current_name(franchise_id)

    def current_name(self, franchise_id: str) -> str:
        for season in reversed(self.seasons):
            franchise = season.franchises.get(franchise_id)
            if franchise:
                return franchise.name
        return f"Franchise {franchise_id}"

    def eras(self, franchise_id: str) -> list[Era]:
        eras: list[Era] = []
        for season in self.seasons:
            franchise = season.franchises.get(franchise_id)
            if franchise is None:
                continue
            if eras and normalize_name(eras[-1].name) == normalize_name(franchise.name):
                eras[-1] = Era(franchise_id, franchise.name, eras[-1].first_year, season.year)
            else:
                eras.append(Era(franchise_id, franchise.name, season.year, season.year))
        return eras

    def era_of(self, franchise_id: str, year: int) -> Era:
        for era in self.eras(franchise_id):
            if era.first_year <= year <= era.last_year:
                return era
        raise KeyError((franchise_id, year))

    def franchise_by_name(self) -> dict[str, str]:
        """Normalized name -> franchise id, over every name ever used."""
        lookup: dict[str, str] = {}
        for season in self.seasons:
            for fid, franchise in season.franchises.items():
                lookup[normalize_name(franchise.name)] = fid
        return lookup

    # --- players -------------------------------------------------------------

    def player_info(self, player_id: str) -> PlayerInfo:
        for season in reversed(self.seasons):
            info = season.players.get(player_id)
            if info is not None:
                return info
        return PlayerInfo.unknown(player_id)

    def rosters(self, year: int) -> dict[int, dict[str, set[str]]]:
        """week -> player id -> franchises whose starters or bench listed the player."""
        out: dict[int, dict[str, set[str]]] = {}
        for number, week in sorted(self.season(year).weeks.items()):
            members: dict[str, set[str]] = defaultdict(set)
            for lineup in week.lineups.values():
                for player_id in lineup.starters + lineup.nonstarters:
                    members[player_id].add(lineup.franchise_id)
            if members:
                out[number] = dict(members)
        return out

    def latest_rostered_week(self) -> tuple[int, int] | None:
        """The newest (year, week) with any roster listed; None when no season has one."""
        for season in reversed(self.seasons):
            weeks = self.rosters(season.year)
            if weeks:
                return season.year, max(weeks)
        return None
