from decimal import Decimal

import pytest
from botocore.exceptions import ClientError

from bdfl.store import TransactionStore


class FakeResource:
    """Scripted stand-in for boto3's DynamoDB resource, for paths moto never exercises."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def Table(self, name):  # noqa: N802 - mirrors boto3's method name
        return None

    def batch_get_item(self, RequestItems):  # noqa: N803 - mirrors boto3's kwarg
        self.calls.append(RequestItems)
        return self.responses.pop(0)


def item(key, state="pending", attempts=0):
    return {
        "pk": key,
        "type": "TRADE",
        "year": 2026,
        "timestamp": 1788400073,
        "franchise_ids": ["0011", "0005"],
        "raw": {"type": "TRADE"},
        "details": {"sides": [], "comments": ""},
        "summary": "x",
        "notify_state": state,
        "notify_attempts": attempts,
        "first_seen_at": 1788400100,
    }


def test_put_new_is_conditional(dynamodb_table):
    resource, name = dynamodb_table
    store = TransactionStore(name, resource=resource)
    assert store.put_new(item("TRADE#1")) is True
    assert store.put_new(item("TRADE#1", state="sent")) is False
    assert store.get_many(["TRADE#1"])["TRADE#1"]["notify_state"] == "pending"


def test_get_many_returns_only_existing_and_handles_more_than_100_keys(dynamodb_table):
    resource, name = dynamodb_table
    store = TransactionStore(name, resource=resource)
    for i in range(120):
        store.put_new(item(f"TRADE#{i}"))
    keys = [f"TRADE#{i}" for i in range(130)]
    found = store.get_many(keys)
    assert len(found) == 120
    assert "TRADE#129" not in found
    assert store.get_many([]) == {}


def test_mark_sent_sets_state_and_timestamp(dynamodb_table):
    resource, name = dynamodb_table
    store = TransactionStore(name, resource=resource)
    store.put_new(item("TRADE#1"))
    store.mark_sent("TRADE#1", at=1788400200)
    row = store.get_many(["TRADE#1"])["TRADE#1"]
    assert row["notify_state"] == "sent"
    assert int(row["notified_at"]) == 1788400200


def test_bump_attempt_increments_and_returns_count(dynamodb_table):
    resource, name = dynamodb_table
    store = TransactionStore(name, resource=resource)
    store.put_new(item("TRADE#1"))
    assert store.bump_attempt("TRADE#1") == 1
    assert store.bump_attempt("TRADE#1") == 2
    assert int(store.get_many(["TRADE#1"])["TRADE#1"]["notify_attempts"]) == 2


def test_mark_failed(dynamodb_table):
    resource, name = dynamodb_table
    store = TransactionStore(name, resource=resource)
    store.put_new(item("TRADE#1"))
    store.mark_failed("TRADE#1")
    assert store.get_many(["TRADE#1"])["TRADE#1"]["notify_state"] == "failed"


def test_get_many_dedupes_keys_and_reads_consistently(dynamodb_table):
    resource, name = dynamodb_table
    store = TransactionStore(name, resource=resource)
    store.put_new(item("TRADE#1"))
    found = store.get_many(["TRADE#1", "TRADE#1", "TRADE#2"])
    assert list(found) == ["TRADE#1"]


def test_get_many_retries_unprocessed_keys_with_backoff():
    name = "tbl"
    fake = FakeResource([
        {"Responses": {name: [{"pk": "A"}]}, "UnprocessedKeys": {name: {"Keys": [{"pk": "B"}], "ConsistentRead": True}}},
        {"Responses": {name: [{"pk": "B"}]}, "UnprocessedKeys": {}},
    ])
    slept = []
    store = TransactionStore(name, resource=fake, sleep=slept.append)
    assert set(store.get_many(["A", "B"])) == {"A", "B"}
    assert len(fake.calls) == 2
    assert fake.calls[1][name]["Keys"] == [{"pk": "B"}]
    assert fake.calls[0][name]["ConsistentRead"] is True
    assert fake.calls[1][name]["ConsistentRead"] is True
    assert slept == [0.05]


def test_get_many_gives_up_after_max_rounds_and_warns(caplog):
    import logging

    name = "tbl"
    stuck = {"Responses": {name: []}, "UnprocessedKeys": {name: {"Keys": [{"pk": "A"}]}}}
    fake = FakeResource([stuck] * 5)
    store = TransactionStore(name, resource=fake, sleep=lambda s: None)
    with caplog.at_level(logging.WARNING):
        assert store.get_many(["A"]) == {}
    assert len(fake.calls) == 5
    assert "gave up with 1 keys unprocessed" in caplog.text


def test_put_new_reraises_other_client_errors(dynamodb_table):
    resource, name = dynamodb_table
    store = TransactionStore(name, resource=resource)
    error = ClientError({"Error": {"Code": "ProvisionedThroughputExceededException"}}, "PutItem")
    store.table.put_item = lambda **kwargs: (_ for _ in ()).throw(error)
    with pytest.raises(ClientError):
        store.put_new(item("TRADE#1"))


def test_put_new_converts_floats_to_decimal(dynamodb_table):
    resource, name = dynamodb_table
    store = TransactionStore(name, resource=resource)
    row = item("TRADE#F")
    row["raw"] = {"bid": 1.5, "nested": [{"x": 2.25}]}
    assert store.put_new(row) is True
    stored = store.get_many(["TRADE#F"])["TRADE#F"]
    assert stored["raw"]["bid"] == Decimal("1.5")
    assert stored["raw"]["nested"][0]["x"] == Decimal("2.25")


def test_mark_sent_only_transitions_from_pending(dynamodb_table, caplog):
    import logging

    resource, name = dynamodb_table
    store = TransactionStore(name, resource=resource)
    store.put_new(item("TRADE#1"))
    assert store.mark_sent("TRADE#1", at=1) is True
    with caplog.at_level(logging.WARNING):
        assert store.mark_sent("TRADE#1", at=2) is False
    assert "was not pending" in caplog.text
    assert int(store.get_many(["TRADE#1"])["TRADE#1"]["notified_at"]) == 1
    store.put_new(item("TRADE#2", state="failed"))
    assert store.mark_sent("TRADE#2", at=3) is False
    assert store.get_many(["TRADE#2"])["TRADE#2"]["notify_state"] == "failed"


def test_updates_on_missing_key_do_not_create_phantom_rows(dynamodb_table):
    resource, name = dynamodb_table
    store = TransactionStore(name, resource=resource)
    with pytest.raises(ClientError):
        store.bump_attempt("GHOST")
    with pytest.raises(ClientError):
        store.mark_failed("GHOST")
    assert store.mark_sent("GHOST", at=1) is False
    assert store.get_many(["GHOST"]) == {}


def test_put_new_keeps_non_finite_floats_as_text(dynamodb_table):
    resource, name = dynamodb_table
    store = TransactionStore(name, resource=resource)
    row = item("TRADE#NF")
    row["raw"] = {"a": float("inf"), "b": float("nan")}
    assert store.put_new(row) is True
    stored = store.get_many(["TRADE#NF"])["TRADE#NF"]
    assert stored["raw"] == {"a": "inf", "b": "nan"}


def test_mark_sent_reraises_other_client_errors(dynamodb_table):
    resource, name = dynamodb_table
    store = TransactionStore(name, resource=resource)
    error = ClientError({"Error": {"Code": "ProvisionedThroughputExceededException"}}, "UpdateItem")
    store.table.update_item = lambda **kwargs: (_ for _ in ()).throw(error)
    with pytest.raises(ClientError):
        store.mark_sent("TRADE#1", at=1)
