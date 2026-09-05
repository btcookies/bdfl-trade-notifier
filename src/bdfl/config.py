"""Runtime settings from environment variables and SSM."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

import boto3

DEFAULT_USER_AGENT = "bdfl-notifier/1.0 (+https://github.com/btcookies/bdfl-trade-notifier)"


@dataclass(frozen=True)
class Settings:
    league_id: str
    table_name: str
    webhook_param_name: str
    notify_max_age_seconds: int
    mfl_user_agent: str
    log_level: str
    webhook_url_override: str | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        return cls(
            league_id=env.get("LEAGUE_ID", "65522"),
            table_name=env["TABLE_NAME"],
            webhook_param_name=env.get("WEBHOOK_PARAM_NAME", "/bdfl/discord/webhook-url"),
            notify_max_age_seconds=int(env.get("NOTIFY_MAX_AGE_SECONDS", "43200")),
            mfl_user_agent=env.get("MFL_USER_AGENT", DEFAULT_USER_AGENT),
            log_level=env.get("LOG_LEVEL", "INFO"),
            webhook_url_override=env.get("DISCORD_WEBHOOK_URL") or None,
        )


def get_webhook_url(settings: Settings, ssm_client=None) -> str:
    if settings.webhook_url_override:
        return settings.webhook_url_override
    client = ssm_client or boto3.client("ssm")
    response = client.get_parameter(Name=settings.webhook_param_name, WithDecryption=True)
    return response["Parameter"]["Value"]
