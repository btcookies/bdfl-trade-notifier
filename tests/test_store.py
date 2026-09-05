from bdfl.store import TransactionStore


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
