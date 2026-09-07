"""Decide whether this run posts a weekly recap or a season wrap, and post it once."""

from __future__ import annotations

import json
import logging
import urllib.parse
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from hof.discord.recap import recap_embed
from hof.discord.wrap import wrap_embed
from hof.model.season import Season
from hof.stats import milestones
from hof.stats.league import League
from hof.stats.model import Model

log = logging.getLogger(__name__)

COMPLETE_AFTER_SECONDS = 40 * 3600  # Sunday 17:00 UTC lock + 40 h = Tuesday 09:00 UTC


class NotifyError(ValueError):
    """Bad configuration: the run cannot post."""


class Webhook(Protocol):
    def post(self, embeds: list[dict]) -> None: ...


@dataclass(frozen=True)
class State:
    season: int
    week: int
    kind: str  # recap or wrap

    @property
    def key(self) -> tuple[int, int]:
        return (self.season, self.week)


@dataclass(frozen=True)
class Decision:
    kind: str  # recap or wrap
    year: int
    week: int


@dataclass(frozen=True)
class Outcome:
    posted: bool
    decision: Decision | None
    reason: str


def webhook_url(env: Mapping[str, str]) -> str:
    """The webhook URL from the environment, checked for shape; never log the value."""
    url = (env.get("DISCORD_WEBHOOK_URL") or "").strip()
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    good_host = host in ("discord.com", "discordapp.com") or host.endswith((".discord.com", ".discordapp.com"))
    if parts.scheme != "https" or not good_host or "/api/webhooks/" not in parts.path:
        raise NotifyError("DISCORD_WEBHOOK_URL is missing or does not look like a Discord webhook URL")
    return url


def load_state(path: Path) -> State | None:
    try:
        raw = json.loads(path.read_text())
        return State(int(raw["season"]), int(raw["week"]), str(raw["kind"]))
    except FileNotFoundError:
        return None
    except (ValueError, KeyError, TypeError) as exc:
        log.warning("ignoring unreadable notify state %s: %s", path, exc)
        return None


def save_state(path: Path, state: State) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state)) + "\n")


def week_complete(season: Season, week: int, now: datetime) -> bool:
    """Locked at least 40 hours ago and every listed matchup has both lineups scored."""
    lock = season.transactions.week_locked_at(week, season.start_week)
    if lock is None or now.timestamp() < lock + COMPLETE_AFTER_SECONDS:
        return False
    listed = season.weeks.get(week)
    if listed is None or not listed.matchups:
        return False
    return all(
        listed.lineups.get(fid) is not None and listed.lineups[fid].score is not None
        for pair in listed.matchups
        for fid in pair
    )


def newest_complete_week(league: League, now: datetime) -> tuple[int, int] | None:
    for season in reversed(league.seasons):
        complete = [week for week in sorted(season.weeks) if week_complete(season, week, now)]
        if complete:
            return season.year, complete[-1]
    return None


def decide(model: Model, state: State | None, now: datetime) -> Decision | None:
    newest = newest_complete_week(model.league, now)
    if newest is None:
        return None
    if state is not None and state.key >= newest:
        return None
    year, week = newest
    final = model.league.season(year).final
    kind = "wrap" if final is not None and final.week == week else "recap"
    return Decision(kind, year, week)


def build_embed(model: Model, decision: Decision, site_url: str) -> dict[str, Any]:
    if decision.kind == "wrap":
        awards = milestones.season_awards(model.league, model.records, decision.year)
        return wrap_embed(model, decision.year, awards, site_url)
    facts = milestones.recap_facts(model.league, model.records, (decision.year, decision.week))
    return recap_embed(facts, site_url)


def run(
    model: Model,
    site_url: str,
    state_path: Path,
    now: datetime,
    webhook: Webhook | None,
    dry_run: bool = False,
    force: tuple[int, int] | None = None,
) -> Outcome:
    """Post the newest complete week once. With dry_run, print the embed instead; with force,
    build the given (year, week) regardless of completion or state (previews only)."""
    if force is not None:
        year, week = force
        final = model.league.season(year).final
        decision: Decision | None = Decision(
            "wrap" if final is not None and final.week == week else "recap", year, week
        )
    else:
        state = load_state(state_path)
        decision = decide(model, state, now)
        if decision is None:
            newest = newest_complete_week(model.league, now)
            reason = "no complete week yet" if newest is None else f"already posted {newest[0]} week {newest[1]}"
            log.info("nothing to post: %s", reason)
            return Outcome(False, None, reason)
    embed = build_embed(model, decision, site_url)
    if dry_run:
        print(json.dumps(embed, ensure_ascii=False, indent=2))
        return Outcome(False, decision, "dry run")
    if webhook is None:
        raise NotifyError("no webhook to post with")
    webhook.post([embed])
    if force is None:
        save_state(state_path, State(decision.year, decision.week, decision.kind))
    log.info("posted %s for %s week %s", decision.kind, decision.year, decision.week)
    return Outcome(True, decision, "posted")


def now_utc() -> datetime:
    return datetime.now(UTC)
