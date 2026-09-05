import boto3
import pytest
from moto import mock_aws

from bdfl.config import Settings, get_webhook_url

BASE_ENV = {"TABLE_NAME": "tbl"}


def test_settings_defaults():
    settings = Settings.from_env(BASE_ENV)
    assert settings.league_id == "65522"
    assert settings.table_name == "tbl"
    assert settings.webhook_param_name == "/bdfl/discord/webhook-url"
    assert settings.notify_max_age_seconds == 43200
    assert settings.mfl_user_agent.startswith("bdfl-notifier/")
    assert settings.log_level == "INFO"
    assert settings.webhook_url_override is None


def test_settings_overrides():
    settings = Settings.from_env({
        **BASE_ENV,
        "LEAGUE_ID": "12345",
        "WEBHOOK_PARAM_NAME": "/x/y",
        "NOTIFY_MAX_AGE_SECONDS": "60",
        "MFL_USER_AGENT": "custom/1",
        "LOG_LEVEL": "DEBUG",
        "DISCORD_WEBHOOK_URL": "https://hook",
    })
    assert settings.league_id == "12345"
    assert settings.webhook_param_name == "/x/y"
    assert settings.notify_max_age_seconds == 60
    assert settings.mfl_user_agent == "custom/1"
    assert settings.log_level == "DEBUG"
    assert settings.webhook_url_override == "https://hook"


def test_settings_requires_table_name():
    with pytest.raises(KeyError):
        Settings.from_env({})


def test_get_webhook_url_prefers_override():
    settings = Settings.from_env({**BASE_ENV, "DISCORD_WEBHOOK_URL": "https://hook"})
    assert get_webhook_url(settings) == "https://hook"


@mock_aws
def test_get_webhook_url_reads_secure_string_from_ssm():
    ssm = boto3.client("ssm", region_name="us-east-1")
    ssm.put_parameter(Name="/bdfl/discord/webhook-url", Value="https://secret", Type="SecureString")
    settings = Settings.from_env(BASE_ENV)
    assert get_webhook_url(settings, ssm_client=ssm) == "https://secret"
