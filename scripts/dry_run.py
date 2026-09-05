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
from datetime import UTC, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from bdfl.config import DEFAULT_USER_AGENT  # noqa: E402
from bdfl.discord import DiscordWebhook  # noqa: E402
from bdfl.messages import trade_embed, waiver_messages  # noqa: E402
from bdfl.mfl import MflClient  # noqa: E402
from bdfl.models import Trade, parse_transactions, referenced_player_ids  # noqa: E402
from bdfl.poller import build_details  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", default=os.environ.get("LEAGUE_ID", "65522"))
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--send", action="store_true", help="post to DISCORD_WEBHOOK_URL")
    args = parser.parse_args()

    mfl = MflClient(args.league, os.environ.get("MFL_USER_AGENT", DEFAULT_USER_AGENT))
    league = mfl.detect_league(datetime.now(tz=UTC))
    print(f"league: {league.name} | year: {league.year} | franchises: {len(league.franchises)}",
          file=sys.stderr)

    records = sorted(parse_transactions(mfl.transactions(league.year, days=args.days)),
                     key=lambda r: r.timestamp)
    players = mfl.players(league.year, referenced_player_ids(records))

    messages: list[list[dict]] = []
    claims = []
    for record in records:
        details = build_details(record, league, players)
        if isinstance(record, Trade):
            messages.append([trade_embed(record, details, league)])
        else:
            claims.append((record, details))
    messages += [embeds for embeds, _ in waiver_messages(claims, league)]

    print(json.dumps(messages, indent=2, ensure_ascii=False))
    print(f"{len(records)} transactions in the last {args.days} days -> {len(messages)} messages",
          file=sys.stderr)

    if args.send:
        url = os.environ.get("DISCORD_WEBHOOK_URL")
        if not url:
            sys.exit("--send requires DISCORD_WEBHOOK_URL in the environment")
        webhook = DiscordWebhook(url)
        for embeds in messages:
            webhook.post(embeds)
        print(f"sent {len(messages)} messages", file=sys.stderr)


if __name__ == "__main__":
    main()
