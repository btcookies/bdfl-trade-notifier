from pathlib import Path

import pytest

from hof.config import Config, ConfigError, HallRules, Manager

REPO_CONFIG = Path(__file__).resolve().parents[2] / "data" / "config.toml"


def test_loads_the_repo_config():
    config = Config.load(REPO_CONFIG)
    assert config.league_id == "65522"
    assert config.site_base_url == "https://btcookies.github.io/bdfl-trade-notifier/"
    assert config.league_id_for(2016) == "79873"
    assert config.league_id_for(2020) == "65522"
    assert config.hall == HallRules(500.0, 30, 2, 100.0)
    assert config.managers == ()


def test_from_dict_applies_defaults_and_normalizes_base_url():
    config = Config.from_dict({"league": {"id": "1", "site_base_url": "https://x.test"}})
    assert config.site_base_url == "https://x.test/"
    assert config.league_overrides == {}
    assert config.hall == HallRules()


def test_managers_are_parsed():
    config = Config.from_dict(
        {
            "league": {"id": "1", "site_base_url": "https://x.test/"},
            "managers": [{"franchise": "0001", "name": " Pat ", "from": 2016}],
        }
    )
    assert config.managers == (Manager("0001", "Pat", 2016),)


def test_hall_of_fame_thresholds_are_read_from_the_config():
    config = Config.from_dict(
        {
            "league": {"id": "1", "site_base_url": "https://x.test/"},
            "hall_of_fame": {
                "player_min_vor": 250.0,
                "player_min_starts": 12,
                "franchise_min_titles": 1,
                "watch_list_margin": 50.0,
            },
        }
    )
    assert config.hall == HallRules(250.0, 12, 1, 50.0)


@pytest.mark.parametrize(
    "raw, message",
    [
        ({"league": {"site_base_url": "https://x.test/"}}, "league.id"),
        ({"league": {"id": "1", "site_base_url": "http://x.test/"}}, "site_base_url"),
        ({"league": {"id": "1", "site_base_url": "https://x.test/"}, "seasons": {"overrides": {"abc": "1"}}}, "overrides"),
        ({"league": {"id": "1", "site_base_url": "https://x.test/"}, "managers": [{"name": "x"}]}, "managers"),
    ],
)
def test_invalid_config_raises(raw, message):
    with pytest.raises(ConfigError, match=message):
        Config.from_dict(raw)


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError, match="missing"):
        Config.load(tmp_path / "config.toml")
