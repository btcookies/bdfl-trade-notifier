#!/usr/bin/env python3
"""Fetch recent MFL transactions and print the Discord messages the bot would post.

Usage:
  python scripts/dry_run.py [--league 65522] [--days 7]
  DISCORD_WEBHOOK_URL=... python scripts/dry_run.py --send   # actually posts them
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bdfl.config import DEFAULT_USER_AGENT, ConfigError, validate_webhook_url  # noqa: E402
from bdfl.discord import DiscordError, DiscordWebhook  # noqa: E402
from bdfl.mfl import MflClient  # noqa: E402
from bdfl.models import parse_transactions, referenced_player_ids  # noqa: E402
from bdfl.poller import POST_SPACING_SECONDS, build_batches, build_details  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", default=os.environ.get("LEAGUE_ID", "65522"))
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--send", action="store_true", help="post to DISCORD_WEBHOOK_URL")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be at least 1")

    mfl = MflClient(args.league, os.environ.get("MFL_USER_AGENT", DEFAULT_USER_AGENT))
    league = mfl.detect_league(datetime.now(tz=UTC))
    print(f"league: {league.name} | year: {league.year} | franchises: {len(league.franchises)}",
          file=sys.stderr)

    records = sorted(parse_transactions(mfl.transactions(league.year, days=args.days)),
                     key=lambda r: r.timestamp)
    players = mfl.players(league.year, referenced_player_ids(records))

    batches = build_batches([(record, build_details(record, league, players)) for record in records],
                            league)
    messages = [embeds for embeds, _ in batches]

    print(json.dumps(messages, indent=2, ensure_ascii=False))
    print(f"{len(records)} transactions in the last {args.days} days -> {len(messages)} messages",
          file=sys.stderr)

    if args.send:
        url = (os.environ.get("DISCORD_WEBHOOK_URL") or "").strip()
        if not url:
            sys.exit("--send requires DISCORD_WEBHOOK_URL in the environment")
        try:
            validate_webhook_url(url)
        except ConfigError as exc:
            sys.exit(f"DISCORD_WEBHOOK_URL rejected: {exc}")
        webhook = DiscordWebhook(url)
        total = len(messages)
        for index, embeds in enumerate(messages, start=1):
            if index > 1:
                time.sleep(POST_SPACING_SECONDS)
            try:
                webhook.post(embeds)
            except DiscordError as exc:
                print(f"failed on message {index}/{total}: {exc}", file=sys.stderr)
                sys.exit(1)
            print(f"sent {index}/{total}", file=sys.stderr)


if __name__ == "__main__":
    main()
