"""Command line: python -m hof [--data DIR] [--config FILE] {fetch,stats,build,notify}."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests

# bdfl lives under src/, which is only on sys.path via pytest's pythonpath setting;
# running `python -m hof` directly needs the same path scripts/dry_run.py adds by hand.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bdfl.discord import DiscordWebhook  # noqa: E402
from bdfl.mfl import MflClient, RequestPacer  # noqa: E402
from hof import fetch
from hof.config import Config
from hof.discord import notify
from hof.site.build import build_site
from hof.snapshots import load_all
from hof.stats.model import compute


def client_factory(session: requests.Session):
    """Build MFL clients that share one HTTP session and one request pacer, one client per
    league id -- sharing the pacer, not just the session, matters because a season's history
    can span league ids (e.g. 2016's), and a freshly built client for a new league id must not
    fire immediately just because it has no memory of the *other* client's last request."""
    pacer = RequestPacer()

    def make(league_id: str) -> MflClient:
        return MflClient(league_id=league_id, user_agent=fetch.USER_AGENT, session=session, pacer=pacer)

    return make


def print_report(model, rules) -> None:
    """A calibration report: what the Hall of Fame looks like under the config thresholds and nearby ones."""
    league = model.league
    print(f"seasons: {league.seasons[0].year}–{league.seasons[-1].year}, through {model.through}")
    print("champions:", ", ".join(f"{y} {league.current_name(c)}" for y, c, _ in model.champions))
    print(f"\nHall of Fame at vor>={rules.player_min_vor:g}, starts>={rules.player_min_starts}: {len(model.hall.players)} players")
    for plaque in model.hall.players:
        print(f"  {plaque.class_year}  {plaque.name:<24} {plaque.position:<3} GS={plaque.starts:<4} pts={plaque.points:8.1f} vor={plaque.vor:7.1f} titles={plaque.titles}")
    print("\nplayers clearing each threshold (with the configured minimum starts):")
    careers = [c for c in model.careers.values() if c.starts >= rules.player_min_starts]
    for threshold in (250, 300, 400, 500, 600, 800):
        print(f"  vor>={threshold}: {sum(1 for c in careers if c.vor >= threshold)}")
    print(f"\nfranchise plaques at {rules.franchise_min_titles} titles: " + ", ".join(f"{p.name} ({p.titles})" for p in model.hall.franchises))
    print("\nwatch list:")
    for entry in model.hall.watch_list[:10]:
        print(f"  {entry.name:<24} vor={entry.vor:7.1f} needs {entry.needed_vor:g} more, starts={entry.starts}")
    print("\nrecords book, top entry per table:")
    for table in model.records:
        if table.entries:
            top = table.entries[0]
            print(f"  {table.title:<45} {top.holder:<28} {top.value:>8} {top.detail}")
    latest = model.analytics.get(league.latest.year)
    if latest is not None and latest.final_power:
        top = latest.final_power[0]
        print(f"\n{latest.year} power #1 through week {latest.power_week}: {top.name} ({top.score:.3f}); "
              f"awards leader: {', '.join(league.current_name(f) for f in latest.awards_leaders)} ({latest.awards_leader_count})")
    print(f"\ntrades: {len(model.trades)} ({sum(1 for t in model.trades if t.pending)} pending)")
    print("drafts:", ", ".join(f"{d.year} ({d.rounds} rounds{', startup' if d.startup else ''})" for d in model.drafts))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hof", description="BDFL Hall of Records")
    parser.add_argument("--data", type=Path, default=Path("data"), help="data directory (default: data)")
    parser.add_argument("--config", type=Path, help="config file (default: <data>/config.toml)")
    parser.add_argument("--log-level", default="INFO")
    commands = parser.add_subparsers(dest="command", required=True)
    fetch_parser = commands.add_parser("fetch", help="download MFL snapshots for every incomplete season")
    fetch_parser.add_argument(
        "--year", type=int, action="append", help="only this season; repeat for several"
    )
    commands.add_parser("stats", help="compute everything and print a calibration report")
    build_parser = commands.add_parser("build", help="render the site into a directory")
    build_parser.add_argument("--out", type=Path, default=Path("dist"), help="output directory (default: dist)")
    notify_parser = commands.add_parser("notify", help="post the newest complete week's recap or the season wrap to Discord")
    notify_parser.add_argument("--dry-run", action="store_true", help="print the embed instead of posting; touches nothing")
    notify_parser.add_argument(
        "--year",
        type=int,
        help="with --week: build this week regardless of completion or state; "
        "without --dry-run this really posts to Discord and does not update the dedupe state",
    )
    notify_parser.add_argument(
        "--week",
        type=int,
        help="with --year: build this week regardless of completion or state; "
        "without --dry-run this really posts to Discord and does not update the dedupe state",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level.upper(), format="%(levelname)s %(name)s: %(message)s")
    config = Config.load(args.config or args.data / "config.toml")

    if args.command == "fetch":
        fetched = fetch.run(
            args.data, config, datetime.now(UTC), client_factory(requests.Session()), years=args.year
        )
        print(f"fetched {len(fetched)} season(s): {fetched}")
        return 0
    if args.command == "stats":
        model = compute(load_all(args.data), config.hall, config.award_labels)
        print_report(model, config.hall)
        return 0
    if args.command == "build":
        model = compute(load_all(args.data), config.hall, config.award_labels)
        build_site(model, config, args.out)
        pages = sum(1 for _ in args.out.rglob("index.html"))
        print(f"built {pages} pages into {args.out}")
        return 0
    if args.command == "notify":
        if (args.year is None) != (args.week is None):
            parser.error("--year and --week go together")
        force = (args.year, args.week) if args.year is not None else None
        model = compute(load_all(args.data), config.hall, config.award_labels)
        state_path = args.data / "notify-state.json"
        if args.dry_run:
            outcome = notify.run(model, config.site_base_url, state_path, notify.now_utc(), None, dry_run=True, force=force)
        else:
            try:
                url = notify.webhook_url(os.environ)
            except notify.NotifyError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            outcome = notify.run(model, config.site_base_url, state_path, notify.now_utc(), DiscordWebhook(url), force=force)
        print(f"{'posted' if outcome.posted else 'nothing posted'}: {outcome.reason}"
              + (f" ({outcome.decision.kind} {outcome.decision.year} week {outcome.decision.week})" if outcome.decision else ""))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
