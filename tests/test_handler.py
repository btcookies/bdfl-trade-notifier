import logging

import pytest

import handler
from bdfl.config import Settings
from bdfl.poller import PollResult


class FakePoller:
    def __init__(self):
        self.runs = 0
        self.last_result = None

    def run(self):
        self.runs += 1
        self.last_result = PollResult(league_year=2026, fetched=2, new=1, sent=1, duration_ms=12)
        return self.last_result


def test_handler_builds_poller_once_and_returns_result(monkeypatch, caplog):
    fake = FakePoller()
    built = []

    def build(settings):
        built.append(settings)
        return fake

    monkeypatch.setenv("TABLE_NAME", "tbl")
    monkeypatch.setattr(handler, "build_poller", build)
    monkeypatch.setattr(handler, "_poller", None)

    with caplog.at_level(logging.INFO):
        first = handler.handler({}, None)
        second = handler.handler({}, None)

    assert first == {
        "league_year": 2026, "fetched": 2, "new": 1, "skipped": 0,
        "sent": 1, "failed": 0, "deferred": 0, "store_errors": 0, "backoff": False, "duration_ms": 12,
    }
    assert second == first
    assert fake.runs == 2
    assert len(built) == 1
    assert built[0].table_name == "tbl"
    assert caplog.text.count('"event": "poll"') == 2


def test_handler_logs_summary_even_when_run_raises(monkeypatch, caplog):
    class RaisingPoller:
        def __init__(self):
            self.last_result = None

        def run(self):
            self.last_result = PollResult(league_year=2026, fetched=3, backoff=False, duration_ms=5)
            raise RuntimeError("boom")

    monkeypatch.setenv("TABLE_NAME", "tbl")
    monkeypatch.setattr(handler, "build_poller", lambda settings: RaisingPoller())
    monkeypatch.setattr(handler, "_poller", None)
    with caplog.at_level(logging.INFO), pytest.raises(RuntimeError):
        handler.handler({}, None)
    assert '"event": "poll"' in caplog.text
    assert '"fetched": 3' in caplog.text


def test_build_poller_wires_real_components_without_network(monkeypatch):
    from bdfl.mfl import MflClient
    from bdfl.poller import Poller
    from bdfl.store import TransactionStore

    monkeypatch.setenv("TABLE_NAME", "tbl")
    poller = handler.build_poller(Settings.from_env())
    assert isinstance(poller, Poller)
    assert isinstance(poller.mfl, MflClient)
    assert isinstance(poller.store, TransactionStore)
    assert poller.mfl.league_id == "65522"
    assert poller._webhook is None


def test_failed_build_leaves_global_unset_so_next_invocation_retries(monkeypatch):
    from bdfl.config import ConfigError

    attempts = []

    def failing(settings):
        attempts.append(1)
        raise ConfigError("bad")

    monkeypatch.setenv("TABLE_NAME", "tbl")
    monkeypatch.setattr(handler, "build_poller", failing)
    monkeypatch.setattr(handler, "_poller", None)
    with pytest.raises(ConfigError):
        handler.handler({}, None)
    assert handler._poller is None
    with pytest.raises(ConfigError):
        handler.handler({}, None)
    assert len(attempts) == 2


def test_handler_does_not_raise_root_or_botocore_log_level(monkeypatch):
    monkeypatch.setenv("TABLE_NAME", "tbl")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    root_before = logging.getLogger().level
    handler.build_poller(Settings.from_env())
    assert logging.getLogger().level == root_before
    assert logging.getLogger("bdfl").level == logging.DEBUG
    assert logging.getLogger("botocore").level == logging.WARNING
