"""DynamoDB-backed store that doubles as the notification outbox.

The conditional put in :meth:`TransactionStore.put_new` is the dedupe guarantee: only
one writer can ever create a given ``pk``, so only that writer notifies. The batch read
in :meth:`TransactionStore.get_many` is purely a cost optimization -- it lets the poller
skip transactions it has already handled without paying for a write. Never treat a miss
from the read as permission to notify; the put decides.

Reads are strongly consistent (``ConsistentRead``), so a row written moments earlier by
a previous invocation is visible.

DynamoDB returns numeric attributes as :class:`decimal.Decimal`, not ``int`` or
``float``. Callers must coerce them (``int(row["notify_attempts"])``) before doing
arithmetic or comparing against plain numbers.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

log = logging.getLogger(__name__)

BATCH_GET_LIMIT = 100
# Bounded timeouts and three total attempts keep any single DynamoDB call well inside the 30 s Lambda budget.
DYNAMO_CONFIG = Config(
    connect_timeout=2, read_timeout=5, retries={"total_max_attempts": 3, "mode": "standard"}
)
MAX_BATCH_GET_ROUNDS = 5


def _to_dynamo(value: Any) -> Any:
    """DynamoDB rejects floats; convert them to Decimal recursively."""
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)  # DynamoDB rejects NaN and infinity; keep the text instead
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_dynamo(v) for v in value]
    return value


class TransactionStore:
    """Dedupe store and notification outbox for one DynamoDB table."""

    def __init__(
        self,
        table_name: str,
        resource=None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Bind to ``table_name``, optionally with an injected resource and sleep."""
        self.resource = resource or boto3.resource("dynamodb", config=DYNAMO_CONFIG)
        self.table_name = table_name
        self.table = self.resource.Table(table_name)
        self.sleep = sleep

    def get_many(self, keys: list[str]) -> dict[str, dict]:
        """Strongly consistent batch read of the rows that exist, keyed by ``pk``."""
        found: dict[str, dict] = {}
        unique = list(dict.fromkeys(keys))
        for start in range(0, len(unique), BATCH_GET_LIMIT):
            chunk = unique[start : start + BATCH_GET_LIMIT]
            request = {
                self.table_name: {
                    "Keys": [{"pk": k} for k in chunk],
                    "ConsistentRead": True,
                }
            }
            unprocessed: list[dict[str, str]] = []
            for attempt in range(MAX_BATCH_GET_ROUNDS):
                response = self.resource.batch_get_item(RequestItems=request)
                for row in response.get("Responses", {}).get(self.table_name, []):
                    found[row["pk"]] = row
                request = response.get("UnprocessedKeys") or {}
                unprocessed = request.get(self.table_name, {}).get("Keys") or []
                if not unprocessed:
                    break
                if attempt < MAX_BATCH_GET_ROUNDS - 1:
                    self.sleep(0.05 * 2**attempt)
            else:
                log.warning("batch get gave up with %s keys unprocessed", len(unprocessed))
        return found

    def put_new(self, item: dict) -> bool:
        """Insert only if the key is absent. Returns False when it already exists."""
        try:
            self.table.put_item(
                Item=_to_dynamo(item), ConditionExpression="attribute_not_exists(pk)"
            )
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def mark_sent(self, key: str, at: int) -> bool:
        """Move a pending row to sent. Returns False if it was not pending."""
        try:
            self.table.update_item(
                Key={"pk": key},
                UpdateExpression="SET notify_state = :state, notified_at = :at",
                ConditionExpression="notify_state = :pending",
                ExpressionAttributeValues={":state": "sent", ":at": at, ":pending": "pending"},
            )
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                log.warning("%s was not pending when marking sent; leaving it", key)
                return False
            raise

    def bump_attempt(self, key: str) -> int:
        """Increment the row's attempt counter and return the new count; raises ClientError if the row is missing."""
        response = self.table.update_item(
            Key={"pk": key},
            UpdateExpression="SET notify_attempts = if_not_exists(notify_attempts, :zero) + :one",
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeValues={":zero": 0, ":one": 1},
            ReturnValues="UPDATED_NEW",
        )
        return int(response["Attributes"]["notify_attempts"])

    def mark_failed(self, key: str) -> None:
        """Mark an existing row as permanently failed; raises ClientError if the row is missing."""
        self.table.update_item(
            Key={"pk": key},
            UpdateExpression="SET notify_state = :state",
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeValues={":state": "failed"},
        )
