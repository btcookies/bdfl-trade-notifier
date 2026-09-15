from pathlib import Path

import pytest

from hof import __main__ as cli
from hof.config import ConfigError

CONFIG = Path(__file__).resolve().parents[2] / "data" / "config.toml"


def test_fetch_command_calls_run_with_years(monkeypatch, tmp_path, capsys):
    seen = {}

    def fake_run(data_dir, config, now, client_factory, years=None):
        seen.update(data_dir=data_dir, league=config.league_id, years=years)
        assert client_factory("79873").league_id == "79873"
        return [2020]

    monkeypatch.setattr(cli.fetch, "run", fake_run)

    code = cli.main(["--data", str(tmp_path), "--config", str(CONFIG), "fetch", "--year", "2020"])

    assert code == 0
    assert seen == {"data_dir": tmp_path, "league": "65522", "years": [2020]}
    assert "fetched 1 season(s): [2020]" in capsys.readouterr().out


def test_missing_config_is_a_clean_error(tmp_path):
    with pytest.raises(ConfigError):
        cli.main(["--data", str(tmp_path), "fetch"])


def test_stats_command_prints_a_report(tmp_path, fixtures_dir, capsys):
    code = cli.main(["--data", str(fixtures_dir), "--config", str(CONFIG), "stats"])
    assert code == 0
    out = capsys.readouterr().out
    assert "champions: 2020 Marcus Peters' Peter Peckers" in out
    assert "Hall of Fame at vor>=500" in out
    assert "records book, top entry per table:" in out
    assert "2020 power #1 through week 13:" in out and "awards leader:" in out


def test_notify_dry_run_prints_an_embed(tmp_path, fixtures_dir, capsys):
    code = cli.main(["--data", str(fixtures_dir), "--config", str(CONFIG), "notify", "--dry-run", "--year", "2020", "--week", "16"])
    assert code == 0
    out = capsys.readouterr().out
    assert '"title": "🏆 2020 season wrap"' in out
    assert "Marcus Peters' Peter Peckers" in out


def test_notify_without_a_webhook_url_fails_clearly(tmp_path, fixtures_dir, monkeypatch, capsys):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    code = cli.main(["--data", str(fixtures_dir), "--config", str(CONFIG), "notify", "--year", "2020", "--week", "16"])
    assert code == 1
    assert "DISCORD_WEBHOOK_URL" in capsys.readouterr().err
