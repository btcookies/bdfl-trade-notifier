"""Runtime settings from environment variables and SSM."""

from __future__ import annotations

import logging
import os
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import boto3
from botocore.config import Config

DEFAULT_USER_AGENT = "bdfl-notifier/1.0 (+https://github.com/btcookies/bdfl-trade-notifier)"

_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

# Three total attempts of at most 5 s each keep a cold-start SSM read inside the 30 s Lambda budget.
SSM_CONFIG = Config(
    connect_timeout=2, read_timeout=3, retries={"total_max_attempts": 3, "mode": "standard"}
)

log = logging.getLogger(__name__)


class ConfigError(ValueError):
    """A required setting is missing or invalid."""


def _get(env: Mapping[str, str], key: str, default: str | None = None) -> str | None:
    """Return the stripped value, or the default when the variable is unset or blank."""
    value = (env.get(key) or "").strip()
    return value or default


def _validate_webhook_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    hostname = parts.hostname or ""
    host_ok = hostname in ("discord.com", "discordapp.com") or hostname.endswith(
        (".discord.com", ".discordapp.com")
    )
    if parts.scheme != "https" or not host_ok or "/webhooks/" not in parts.path:
        raise ConfigError("webhook URL does not look like a Discord webhook")
    return url


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the Lambda, loaded from environment variables."""

    league_id: str
    table_name: str
    webhook_param_name: str
    notify_max_age_seconds: int
    mfl_user_agent: str
    log_level: str
    webhook_url_override: str | None = field(repr=False)

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        """Build Settings from environment variables, treating blank values as unset."""
        table_name = _get(env, "TABLE_NAME")
        if table_name is None:
            raise ConfigError("TABLE_NAME is required")

        raw_max_age = _get(env, "NOTIFY_MAX_AGE_SECONDS", "43200")
        try:
            notify_max_age_seconds = int(raw_max_age)
        except ValueError:
            raise ConfigError(
                f"NOTIFY_MAX_AGE_SECONDS must be an integer, got {raw_max_age!r}"
            ) from None
        if notify_max_age_seconds <= 0:
            raise ConfigError("NOTIFY_MAX_AGE_SECONDS must be positive")

        log_level = _get(env, "LOG_LEVEL", "INFO").upper()
        if log_level not in _LOG_LEVELS:
            log.warning("unknown LOG_LEVEL %r; using INFO", log_level)
            log_level = "INFO"

        return cls(
            league_id=_get(env, "LEAGUE_ID", "65522"),
            table_name=table_name,
            webhook_param_name=_get(env, "WEBHOOK_PARAM_NAME", "/bdfl/discord/webhook-url"),
            notify_max_age_seconds=notify_max_age_seconds,
            mfl_user_agent=_get(env, "MFL_USER_AGENT", DEFAULT_USER_AGENT),
            log_level=log_level,
            webhook_url_override=_get(env, "DISCORD_WEBHOOK_URL", None),
        )


def get_webhook_url(settings: Settings, ssm_client: Any = None) -> str:
    """Return the Discord webhook URL; it is a secret that must never be logged, and callers should cache it for the container's life."""
    if settings.webhook_url_override:
        return _validate_webhook_url(settings.webhook_url_override)
    client = ssm_client or boto3.client("ssm", config=SSM_CONFIG)
    response = client.get_parameter(Name=settings.webhook_param_name, WithDecryption=True)
    value = response["Parameter"]["Value"].strip()
    return _validate_webhook_url(value)
