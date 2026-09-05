import boto3
import pytest
from moto import mock_aws

from bdfl.config import ConfigError, Settings, get_webhook_url

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
        "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/1/hook",
    })
    assert settings.league_id == "12345"
    assert settings.webhook_param_name == "/x/y"
    assert settings.notify_max_age_seconds == 60
    assert settings.mfl_user_agent == "custom/1"
    assert settings.log_level == "DEBUG"
    assert settings.webhook_url_override == "https://discord.com/api/webhooks/1/hook"


def test_settings_requires_table_name():
    with pytest.raises(ConfigError, match="TABLE_NAME"):
        Settings.from_env({})


def test_get_webhook_url_prefers_override():
    settings = Settings.from_env({**BASE_ENV, "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/1/hook"})
    assert get_webhook_url(settings) == "https://discord.com/api/webhooks/1/hook"


@mock_aws
def test_get_webhook_url_reads_secure_string_from_ssm():
    ssm = boto3.client("ssm", region_name="us-east-1")
    ssm.put_parameter(Name="/bdfl/discord/webhook-url", Value="https://discord.com/api/webhooks/1/secret", Type="SecureString")
    settings = Settings.from_env(BASE_ENV)
    assert get_webhook_url(settings, ssm_client=ssm) == "https://discord.com/api/webhooks/1/secret"


def test_blank_env_values_count_as_unset():
    settings = Settings.from_env({**BASE_ENV, "LEAGUE_ID": "  ", "MFL_USER_AGENT": "", "LOG_LEVEL": " "})
    assert settings.league_id == "65522"
    assert settings.mfl_user_agent.startswith("bdfl-notifier/")
    assert settings.log_level == "INFO"
    assert Settings.from_env({"TABLE_NAME": " tbl "}).table_name == "tbl"


def test_notify_max_age_must_be_a_positive_integer():
    with pytest.raises(ConfigError, match="integer"):
        Settings.from_env({**BASE_ENV, "NOTIFY_MAX_AGE_SECONDS": "soon"})
    with pytest.raises(ConfigError, match="positive"):
        Settings.from_env({**BASE_ENV, "NOTIFY_MAX_AGE_SECONDS": "0"})
    with pytest.raises(ConfigError, match="positive"):
        Settings.from_env({**BASE_ENV, "NOTIFY_MAX_AGE_SECONDS": "-5"})


def test_log_level_is_normalized_and_unknown_falls_back(caplog):
    import logging

    assert Settings.from_env({**BASE_ENV, "LOG_LEVEL": "debug"}).log_level == "DEBUG"
    with caplog.at_level(logging.WARNING):
        assert Settings.from_env({**BASE_ENV, "LOG_LEVEL": "verbose"}).log_level == "INFO"
    assert "unknown LOG_LEVEL" in caplog.text


def test_repr_hides_the_webhook_override():
    settings = Settings.from_env({**BASE_ENV, "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/1/SECRET"})
    assert "SECRET" not in repr(settings)
    assert "SECRET" not in str(settings)


def test_get_webhook_url_does_not_touch_ssm_when_overridden():
    class Boom:
        def get_parameter(self, **kwargs):
            raise AssertionError("SSM must not be called")

    settings = Settings.from_env({**BASE_ENV, "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/1/x"})
    assert get_webhook_url(settings, ssm_client=Boom()) == "https://discord.com/api/webhooks/1/x"


@mock_aws
def test_get_webhook_url_strips_and_validates_the_parameter():
    ssm = boto3.client("ssm", region_name="us-east-1")
    ssm.put_parameter(Name="/bdfl/discord/webhook-url", Value="https://discord.com/api/webhooks/1/x\n", Type="SecureString")
    assert get_webhook_url(Settings.from_env(BASE_ENV), ssm_client=ssm) == "https://discord.com/api/webhooks/1/x"
    ssm.put_parameter(Name="/bdfl/discord/webhook-url", Value="https://discord.com/channels/1/2", Type="SecureString", Overwrite=True)
    with pytest.raises(ConfigError) as info:
        get_webhook_url(Settings.from_env(BASE_ENV), ssm_client=ssm)
    assert "channels" not in str(info.value)


def test_override_is_validated_too():
    settings = Settings.from_env({**BASE_ENV, "DISCORD_WEBHOOK_URL": "http://example.com/api/webhooks/1/x"})
    with pytest.raises(ConfigError):
        get_webhook_url(settings)


@mock_aws
def test_missing_parameter_propagates_client_error():
    from botocore.exceptions import ClientError

    ssm = boto3.client("ssm", region_name="us-east-1")
    with pytest.raises(ClientError):
        get_webhook_url(Settings.from_env(BASE_ENV), ssm_client=ssm)


def test_ssm_client_config_is_bounded():
    from bdfl.config import SSM_CONFIG

    config = boto3.client("ssm", region_name="us-east-1", config=SSM_CONFIG).meta.config
    assert (config.connect_timeout, config.read_timeout) == (2, 3)
    assert config.retries == {"mode": "standard", "total_max_attempts": 3}
