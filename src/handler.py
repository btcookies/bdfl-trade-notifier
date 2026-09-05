"""Lambda entry point: one poll per invocation, one poller per container."""

from __future__ import annotations

import json
import logging

from bdfl.config import Settings, get_webhook_url
from bdfl.discord import DiscordWebhook
from bdfl.mfl import MflClient
from bdfl.poller import Poller
from bdfl.store import TransactionStore

log = logging.getLogger("bdfl")
_poller: Poller | None = None


def build_poller(settings: Settings) -> Poller:
    logging.getLogger().setLevel(settings.log_level)
    mfl = MflClient(settings.league_id, settings.mfl_user_agent)
    store = TransactionStore(settings.table_name)
    return Poller(
        settings,
        mfl,
        store,
        webhook_factory=lambda: DiscordWebhook(get_webhook_url(settings)),
    )


def handler(event, context):
    global _poller
    if _poller is None:
        _poller = build_poller(Settings.from_env())
    try:
        return _poller.run().as_dict()
    finally:
        if _poller.last_result is not None:
            log.info(json.dumps({"event": "poll", **_poller.last_result.as_dict()}))
