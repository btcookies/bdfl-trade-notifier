import pytest
from botocore.exceptions import ClientError

from bdfl.config import Settings
from bdfl.discord import DiscordError, DiscordPermanentError
from bdfl.mfl import MflThrottled
from bdfl.models import LeagueInfo, Player
from bdfl.poller import (
    BACKOFF_SECONDS,
    LEAGUE_TTL_SECONDS,
    MAX_ATTEMPTS,
    POST_SPACING_SECONDS,
    NotifyFailed,
    Poller,
)
from bdfl.store import TransactionStore

NOW = 1788400200
LEAGUE = LeagueInfo(2026, "BDFL", {"0011": "A.J. Mudbone", "0005": "Jeff Janis Fan Club", "0003": "Youth"})
PLAYERS = {
    "13299": Player("13299", "Kittle, George", "SFO", "TE"),
    "15255": Player("15255", "Gainwell, Kenneth", "TBB", "RB"),
    "15733": Player("15733", "Doe, John", "NYG", "WR"),
}
TRADE = {
    "type": "TRADE", "timestamp": str(NOW - 120), "franchise": "0011", "franchise2": "0005",
    "franchise1_gave_up": "15255,", "franchise2_gave_up": "13299,BB_20,", "comments": "",
}
CLAIM_A = {"type": "BBID_WAIVER", "timestamp": str(NOW - 60), "franchise": "0003", "transaction": "15733,|3.00|"}
CLAIM_B = {"type": "BBID_WAIVER", "timestamp": str(NOW - 60), "franchise": "0011", "transaction": "13299,|7.00|"}


def payload(*transactions):
    return {"transactions": {"transaction": list(transactions)}}


class FakeMfl:
    def __init__(self, leagues, payload=None, players=None):
        self.leagues = leagues
        self.payload = payload or {"transactions": {}}
        self.players_map = players or PLAYERS
        self.detect_calls = 0
        self.transactions_calls = 0
        self.players_calls = []
        self.transactions_error = None

    def detect_league(self, now):
        league = self.leagues[min(self.detect_calls, len(self.leagues) - 1)]
        self.detect_calls += 1
        return league

    def transactions(self, year, days=1, types="TRADE,BBID_WAIVER"):
        self.transactions_calls += 1
        if self.transactions_error:
            raise self.transactions_error
        return self.payload

    def players(self, year, ids):
        self.players_calls.append(sorted(ids))
        return {i: self.players_map[i] for i in ids if i in self.players_map}


class FakeWebhook:
    def __init__(self):
        self.posts = []
        self.fail_times = 0
        self.error: Exception = DiscordError("down")

    def post(self, embeds):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise self.error
        self.posts.append(embeds)


class FakeClock:
    def __init__(self, now=NOW):
        self.now = float(now)

    def __call__(self):
        return self.now


@pytest.fixture
def harness(dynamodb_table):
    resource, table_name = dynamodb_table
    settings = Settings.from_env({"TABLE_NAME": table_name})
    store = TransactionStore(table_name, resource=resource)
    webhook = FakeWebhook()
    clock = FakeClock()

    def build(mfl):
        return Poller(
            settings,
            mfl,
            store,
            webhook_factory=lambda: webhook,
            clock=clock,
            sleep=lambda seconds: None,
        )

    return build, store, webhook, clock


def test_new_trade_is_stored_posted_and_marked_sent(harness):
    build, store, webhook, _ = harness
    mfl = FakeMfl([LEAGUE], payload(TRADE))
    result = build(mfl).run()
    assert (result.league_year, result.fetched, result.new, result.skipped, result.sent, result.failed) == (2026, 1, 1, 0, 1, 0)
    assert result.backoff is False
    assert len(webhook.posts) == 1
    assert webhook.posts[0][0]["title"] == "🚨 Trade Completed"
    row = store.get_many([f"TRADE#{NOW - 120}#0011#0005"])[f"TRADE#{NOW - 120}#0011#0005"]
    assert row["notify_state"] == "sent"
    assert int(row["year"]) == 2026
    assert int(row["notified_at"]) == NOW
    assert row["summary"].startswith("A.J. Mudbone gives up: Kenneth Gainwell, TBB RB")
    assert row["details"]["sides"][1]["assets"] == ["George Kittle, SFO TE", "$20 blind bid dollars"]
    assert mfl.players_calls == [["13299", "15255"]]


def test_old_transaction_is_stored_silently(harness):
    build, store, webhook, _ = harness
    old = {**TRADE, "timestamp": str(NOW - 50000)}
    result = build(FakeMfl([LEAGUE], payload(old))).run()
    assert (result.new, result.skipped, result.sent) == (1, 1, 0)
    assert webhook.posts == []
    assert store.get_many([f"TRADE#{NOW - 50000}#0011#0005"])[f"TRADE#{NOW - 50000}#0011#0005"]["notify_state"] == "skipped"


def test_repeat_polls_do_not_repost_or_refetch_players(harness):
    build, _, webhook, _ = harness
    mfl = FakeMfl([LEAGUE], payload(TRADE))
    poller = build(mfl)
    poller.run()
    second = poller.run()
    third = poller.run()
    assert len(webhook.posts) == 1
    assert (second.fetched, second.new, second.sent) == (1, 0, 0)
    assert third.new == 0
    assert mfl.players_calls == [["13299", "15255"]]


def test_discord_failure_leaves_pending_and_next_poll_sends(harness):
    build, store, webhook, _ = harness
    webhook.fail_times = 1
    poller = build(FakeMfl([LEAGUE], payload(TRADE)))
    first = poller.run()
    key = f"TRADE#{NOW - 120}#0011#0005"
    row = store.get_many([key])[key]
    assert (first.sent, first.failed, row["notify_state"], int(row["notify_attempts"])) == (0, 0, "pending", 1)
    second = poller.run()
    assert second.sent == 1
    assert store.get_many([key])[key]["notify_state"] == "sent"
    assert len(webhook.posts) == 1


def test_fifth_failure_marks_failed_and_raises(harness):
    build, store, webhook, _ = harness
    webhook.fail_times = MAX_ATTEMPTS
    poller = build(FakeMfl([LEAGUE], payload(TRADE)))
    for _ in range(MAX_ATTEMPTS - 1):
        poller.run()
    with pytest.raises(NotifyFailed):
        poller.run()
    key = f"TRADE#{NOW - 120}#0011#0005"
    assert store.get_many([key])[key]["notify_state"] == "failed"
    poller.run()
    assert webhook.posts == []


def test_throttle_sets_backoff_then_resumes(harness):
    build, _, _, clock = harness
    mfl = FakeMfl([LEAGUE], payload(TRADE))
    mfl.transactions_error = MflThrottled("429")
    poller = build(mfl)
    with pytest.raises(MflThrottled):
        poller.run()
    mfl.transactions_error = None
    clock.now = NOW + BACKOFF_SECONDS - 1
    assert poller.run().backoff is True
    assert mfl.transactions_calls == 1
    clock.now = NOW + BACKOFF_SECONDS + 1
    result = poller.run()
    assert result.backoff is False
    assert result.sent == 1


def test_league_info_is_cached_for_six_hours(harness):
    build, _, _, clock = harness
    mfl = FakeMfl([LEAGUE])
    poller = build(mfl)
    poller.run()
    clock.now = NOW + LEAGUE_TTL_SECONDS - 10
    poller.run()
    assert mfl.detect_calls == 1
    clock.now = NOW + LEAGUE_TTL_SECONDS + 10
    poller.run()
    assert mfl.detect_calls == 2


def test_unknown_franchise_refreshes_only_on_a_later_run(harness):
    build, _, webhook, clock = harness
    renamed = LeagueInfo(2026, "BDFL", {**LEAGUE.franchises, "0099": "New Team"})
    claim = {**CLAIM_A, "franchise": "0099"}
    mfl = FakeMfl([LEAGUE, renamed], payload(claim))
    poller = build(mfl)
    first = poller.run()
    assert mfl.detect_calls == 1
    assert first.sent == 1
    assert "**Franchise 0099**" in webhook.posts[0][0]["description"]

    later = {**CLAIM_B, "franchise": "0099", "timestamp": str(NOW + 60 - 30)}
    mfl.payload = payload(claim, later)
    clock.now = NOW + 60
    second = poller.run()
    assert mfl.detect_calls == 2
    assert second.sent == 1
    assert "**New Team**" in webhook.posts[1][0]["description"]


def test_waiver_claims_share_one_message_and_trade_gets_its_own(harness):
    build, store, webhook, _ = harness
    result = build(FakeMfl([LEAGUE], payload(TRADE, CLAIM_A, CLAIM_B))).run()
    assert (result.fetched, result.new, result.sent) == (3, 3, 3)
    assert len(webhook.posts) == 2
    titles = [embeds[0]["title"] for embeds in webhook.posts]
    assert titles == ["🚨 Trade Completed", "✅ Waiver Claims Processed"]
    description = webhook.posts[1][0]["description"]
    assert description.index("A.J. Mudbone") < description.index("Youth")
    keys = [f"WAIVER#{NOW - 60}#0003#15733", f"WAIVER#{NOW - 60}#0011#13299"]
    assert {row["notify_state"] for row in store.get_many(keys).values()} == {"sent"}


def test_empty_poll_makes_no_writes_or_posts(harness):
    build, _, webhook, _ = harness
    mfl = FakeMfl([LEAGUE], {"transactions": {}})
    result = build(mfl).run()
    assert (result.fetched, result.new, result.sent) == (0, 0, 0)
    assert webhook.posts == []
    assert mfl.players_calls == []
    assert result.duration_ms >= 0


def test_permanent_discord_error_marks_failed_immediately_and_raises(harness):
    build, store, webhook, _ = harness
    webhook.error = DiscordPermanentError("bad payload")
    webhook.fail_times = 1
    poller = build(FakeMfl([LEAGUE], payload(TRADE)))
    with pytest.raises(NotifyFailed):
        poller.run()
    key = f"TRADE#{NOW - 120}#0011#0005"
    row = store.get_many([key])[key]
    assert (row["notify_state"], int(row["notify_attempts"])) == ("failed", 0)
    result = poller.run()
    assert (result.sent, result.failed) == (0, 0)
    assert webhook.posts == []


def test_posts_are_spaced_apart(harness):
    build, _, webhook, _ = harness
    slept = []
    poller = build(FakeMfl([LEAGUE], payload(TRADE, CLAIM_A, CLAIM_B)))
    poller.sleep = slept.append
    poller.run()
    assert len(webhook.posts) == 2
    assert slept == [POST_SPACING_SECONDS]


def test_store_error_in_failure_path_does_not_abort_the_poll(harness):
    build, store, webhook, _ = harness
    webhook.fail_times = 1
    poller = build(FakeMfl([LEAGUE], payload(TRADE)))
    error = ClientError({"Error": {"Code": "ProvisionedThroughputExceededException"}}, "UpdateItem")

    def boom(key):
        raise error

    store.bump_attempt = boom
    first = poller.run()
    assert (first.sent, first.failed) == (0, 0)
    second = poller.run()
    assert second.sent == 1
