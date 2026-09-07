"""One call that computes everything the site and the Discord posts render."""

from __future__ import annotations

from dataclasses import dataclass

from hof.config import HallRules
from hof.model.season import Season
from hof.stats import careers as careers_mod
from hof.stats import drafts as drafts_mod
from hof.stats import franchises as franchises_mod
from hof.stats import hall as hall_mod
from hof.stats import records as records_mod
from hof.stats import trades as trades_mod
from hof.stats.careers import Career, WeekKey
from hof.stats.drafts import DraftRanking, DraftSummary
from hof.stats.franchises import FranchiseHistory
from hof.stats.hall import Hall
from hof.stats.league import League
from hof.stats.records import RecordTable
from hof.stats.trades import TradeLine


@dataclass
class Model:
    league: League
    careers: dict[str, Career]
    histories: dict[str, FranchiseHistory]
    records: list[RecordTable]
    hall: Hall
    drafts: list[DraftSummary]
    draft_rankings: list[DraftRanking]
    trades: list[TradeLine]
    through: WeekKey | None  # newest (year, week) with a counted game
    champions: list[tuple[int, str, str]]  # (year, champion id, runner-up id), oldest first


def latest_played_week(league: League) -> WeekKey | None:
    for season in reversed(league.seasons):
        games = season.games()
        if games:
            return season.year, max(g.week for g in games)
    return None


def champions(league: League) -> list[tuple[int, str, str]]:
    out = []
    for season in league.seasons:
        final = season.final
        if final is not None and final.winner is not None and final.loser is not None:
            out.append((season.year, final.winner.franchise_id, final.loser.franchise_id))
    return out


def compute(seasons: list[Season], rules: HallRules) -> Model:
    league = League.build(seasons)
    careers = careers_mod.careers(league)
    histories = franchises_mod.all_franchises(league)
    records = records_mod.records_book(league, careers)
    drafts = drafts_mod.draft_summaries(league, careers)
    return Model(
        league=league,
        careers=careers,
        histories=histories,
        records=records,
        hall=hall_mod.hall_of_fame(league, careers, histories, rules),
        drafts=drafts,
        draft_rankings=drafts_mod.draft_rankings(league, drafts),
        trades=trades_mod.trade_ledger(league, careers_mod.stints(league)),
        through=latest_played_week(league),
        champions=champions(league),
    )
