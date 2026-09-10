"""Power rankings: a transparent composite of all-play strength, actual record, and recent form.

    score = 0.5 * all-play % (season to date)
          + 0.3 * win % (ties count half)
          + 0.2 * form, the all-play % over the last three regular-season weeks pooled

Computed after each regular-season week with a counted game. The last regular-season ranking
stands through the playoffs. Ties break on points for, then name.
"""

from __future__ import annotations

from dataclasses import dataclass

from hof.model.season import Season
from hof.stats import allplay
from hof.stats.league import League

WEIGHT_ALLPLAY = 0.5
WEIGHT_RECORD = 0.3
WEIGHT_FORM = 0.2
FORM_WEEKS = 3
FORMULA = (
    "Score = 0.5 × all-play % + 0.3 × win % + 0.2 × form, "
    "where form is all-play % over the last three weeks."
)


@dataclass(frozen=True)
class PowerLine:
    rank: int
    franchise_id: str
    name: str  # the name used that season
    score: float  # three decimals
    allplay_pct: float  # three decimals
    win_pct: float  # three decimals
    form: float  # three decimals
    previous_rank: int | None

    @property
    def movement(self) -> int | None:
        """Places gained (positive) or lost since the previous ranked week; None the first week."""
        return None if self.previous_rank is None else self.previous_rank - self.rank


def ranked_weeks(season: Season) -> list[int]:
    """Regular-season weeks that get a ranking: those with a counted game."""
    return allplay.regular_weeks(season)


def _pct(wins: int, losses: int, ties: int) -> float:
    total = wins + losses + ties
    return (wins + 0.5 * ties) / total if total else 0.0


def _table(league: League, season: Season, through_week: int) -> list[tuple[str, float, float, float, float]]:
    """(franchise id, score, all-play %, win %, form) for every franchise with a counted game
    through the week, best first."""
    weeks = allplay.regular_weeks(season, through_week)
    recent = set(weeks[-FORM_WEEKS:])
    recent_allplay: dict[str, list[int]] = {}
    for row in allplay.all_play_weeks(season, through_week):
        if row.week in recent:
            record = recent_allplay.setdefault(row.franchise_id, [0, 0, 0])
            record[0] += row.wins
            record[1] += row.losses
            record[2] += row.ties
    rows = []
    for line in allplay.standings(league, season, through_week):
        if not line.games:
            continue
        form = _pct(*recent_allplay.get(line.franchise_id, [0, 0, 0]))
        win_pct = _pct(line.wins, line.losses, line.ties)
        score = round(WEIGHT_ALLPLAY * line.allplay_pct + WEIGHT_RECORD * win_pct + WEIGHT_FORM * form, 3)
        rows.append((line.franchise_id, score, line.allplay_pct, win_pct, form, line.points_for, line.name))
    rows.sort(key=lambda r: (-r[1], -r[5], r[6]))
    return [(fid, score, ap, wp, form) for fid, score, ap, wp, form, _, _ in rows]


def rankings(league: League, season: Season, through_week: int | None = None) -> list[PowerLine]:
    """The ranking as of the newest ranked week at or before through_week (every week when None)."""
    weeks = allplay.regular_weeks(season, through_week)
    if not weeks:
        return []
    current = _table(league, season, weeks[-1])
    previous: dict[str, int] = {}
    if len(weeks) > 1:
        previous = {fid: i + 1 for i, (fid, *_) in enumerate(_table(league, season, weeks[-2]))}
    return [
        PowerLine(
            rank=i + 1,
            franchise_id=fid,
            name=league.name_in(fid, season.year),
            score=score,
            allplay_pct=round(ap, 3),
            win_pct=round(wp, 3),
            form=round(form, 3),
            previous_rank=previous.get(fid),
        )
        for i, (fid, score, ap, wp, form) in enumerate(current)
    ]
