"""Per-season analytics: weekly standings with all-play and luck, power rankings, and awards."""

from __future__ import annotations

from dataclasses import dataclass

from hof.model.season import Season
from hof.stats import allplay, power
from hof.stats import awards as awards_mod
from hof.stats.allplay import StandingLine
from hof.stats.awards import Award
from hof.stats.league import League
from hof.stats.power import PowerLine


@dataclass(frozen=True)
class WeekAnalytics:
    week: int
    playoff: bool
    standings: tuple[StandingLine, ...]  # through this week; through the regular season in playoff weeks
    power: tuple[PowerLine, ...]  # empty in playoff weeks
    awards: tuple[Award, ...]


@dataclass(frozen=True)
class SeasonAnalytics:
    year: int
    weeks: tuple[WeekAnalytics, ...]  # ascending; every week with a counted game
    tally: dict[str, dict[str, int]]  # franchise id -> award key -> count
    awards_leaders: tuple[str, ...]  # franchise ids sharing the most awards
    awards_leader_count: int
    luckiest: StandingLine | None
    unluckiest: StandingLine | None

    @property
    def latest(self) -> WeekAnalytics | None:
        return self.weeks[-1] if self.weeks else None

    @property
    def standings(self) -> tuple[StandingLine, ...]:
        return self.latest.standings if self.latest else ()

    def _newest_ranked(self) -> WeekAnalytics | None:
        return next((week for week in reversed(self.weeks) if week.power), None)

    @property
    def final_power(self) -> tuple[PowerLine, ...]:
        """The newest ranking: the last regular-season week's during and after the playoffs."""
        week = self._newest_ranked()
        return week.power if week else ()

    @property
    def power_week(self) -> int | None:
        week = self._newest_ranked()
        return week.week if week else None


def season_analytics(league: League, season: Season, labels: dict[str, str] | None = None) -> SeasonAnalytics:
    weeks: list[WeekAnalytics] = []
    for week in sorted({g.week for g in season.games()}):
        playoff = week > season.last_regular_season_week
        weeks.append(
            WeekAnalytics(
                week=week,
                playoff=playoff,
                standings=tuple(allplay.standings(league, season, None if playoff else week)),
                power=() if playoff else tuple(power.rankings(league, season, week)),
                awards=tuple(awards_mod.week_awards(league, season, week, labels)),
            )
        )
    counts = awards_mod.tally([w.awards for w in weeks], season.franchises)
    leaders, count = awards_mod.leaders(counts)
    played = [line for line in (weeks[-1].standings if weeks else ()) if line.games]
    return SeasonAnalytics(
        year=season.year,
        weeks=tuple(weeks),
        tally=counts,
        awards_leaders=leaders,
        awards_leader_count=count,
        luckiest=min(played, key=lambda line: (-line.luck, line.name), default=None),
        unluckiest=min(played, key=lambda line: (line.luck, line.name), default=None),
    )


def compute(league: League, labels: dict[str, str] | None = None) -> dict[int, SeasonAnalytics]:
    return {season.year: season_analytics(league, season, labels) for season in league.seasons}
