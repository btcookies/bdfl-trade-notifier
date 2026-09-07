"""Command line: python -m hof [--data DIR] [--config FILE] {fetch,stats}."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests

# bdfl lives under src/, which is only on sys.path via pytest's pythonpath setting;
# running `python -m hof` directly needs the same path scripts/dry_run.py adds by hand.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bdfl.mfl import MflClient, RequestPacer  # noqa: E402
from hof import fetch
from hof.config import Config
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
        model = compute(load_all(args.data), config.hall)
        print_report(model, config.hall)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
