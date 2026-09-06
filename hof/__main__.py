"""Command line: python -m hof [--data DIR] [--config FILE] {fetch}."""

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

from bdfl.mfl import MflClient  # noqa: E402
from hof import fetch
from hof.config import Config


def client_factory(session: requests.Session):
    """Build MFL clients that share one HTTP session; one client per league id."""

    def make(league_id: str) -> MflClient:
        return MflClient(league_id=league_id, user_agent=fetch.USER_AGENT, session=session)

    return make


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
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level.upper(), format="%(levelname)s %(name)s: %(message)s")
    config = Config.load(args.config or args.data / "config.toml")

    if args.command == "fetch":
        fetched = fetch.run(
            args.data, config, datetime.now(UTC), client_factory(requests.Session()), years=args.year
        )
        print(f"fetched {len(fetched)} season(s): {fetched}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
