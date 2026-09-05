"""Lambda entry point: one poll per invocation, one poller per container."""

from __future__ import annotations

import logging

from bdfl.config import Settings, get_webhook_url
from bdfl.discord import DiscordWebhook
from bdfl.mfl import MflClient
from bdfl.poller import Poller
from bdfl.store import TransactionStore

log = logging.getLogger("bdfl")
_poller: Poller | None = None


def build_poller(settings: Settings) -> Poller:
    logging.getLogger("bdfl").setLevel(settings.log_level)
    # AWS SDK debug logging would print SSM response bodies, including the webhook secret.
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    # The HTTP transport logs request paths at DEBUG, and the webhook path is the secret.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    mfl = MflClient(settings.league_id, settings.mfl_user_agent)
    store = TransactionStore(settings.table_name)
    return Poller(
        settings,
        mfl,
        store,
        webhook_factory=lambda: DiscordWebhook(get_webhook_url(settings)),
    )


def handler(event: dict, context: object) -> dict:
    global _poller
    if _poller is None:
        _poller = build_poller(Settings.from_env())
    try:
        return _poller.run().as_dict()
    finally:
        if _poller.last_result is not None:
            # Lambda's JSON log format stringifies the message but emits `extra` fields as top-level
            # JSON keys, which is what the template's metric filters read ($.store_errors, $.failed).
            log.info("poll", extra={"event": "poll", **_poller.last_result.as_dict()})
