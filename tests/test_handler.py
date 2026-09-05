import logging

import pytest

import handler
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
    handler._poller = None

    with caplog.at_level(logging.INFO):
        first = handler.handler({}, None)
        second = handler.handler({}, None)

    assert first == {
        "league_year": 2026, "fetched": 2, "new": 1, "skipped": 0,
        "sent": 1, "failed": 0, "backoff": False, "duration_ms": 12,
    }
    assert second == first
    assert fake.runs == 2
    assert len(built) == 1
    assert built[0].table_name == "tbl"
    assert caplog.text.count('"event": "poll"') == 2


def test_handler_logs_summary_even_when_run_raises(monkeypatch, caplog):
    import logging

    from bdfl.poller import PollResult

    class RaisingPoller:
        def __init__(self):
            self.last_result = None

        def run(self):
            self.last_result = PollResult(league_year=2026, fetched=3, backoff=False, duration_ms=5)
            raise RuntimeError("boom")

    monkeypatch.setenv("TABLE_NAME", "tbl")
    monkeypatch.setattr(handler, "build_poller", lambda settings: RaisingPoller())
    handler._poller = None
    with caplog.at_level(logging.INFO), pytest.raises(RuntimeError):
        handler.handler({}, None)
    assert '"event": "poll"' in caplog.text
    assert '"fetched": 3' in caplog.text
