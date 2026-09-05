"""DynamoDB-backed store that doubles as the notification outbox."""

from __future__ import annotations

import boto3
from botocore.exceptions import ClientError

BATCH_GET_LIMIT = 100
MAX_UNPROCESSED_ROUNDS = 5


class TransactionStore:
    def __init__(self, table_name: str, resource=None):
        self.resource = resource or boto3.resource("dynamodb")
        self.table_name = table_name
        self.table = self.resource.Table(table_name)

    def get_many(self, keys: list[str]) -> dict[str, dict]:
        found: dict[str, dict] = {}
        for start in range(0, len(keys), BATCH_GET_LIMIT):
            request = {self.table_name: {"Keys": [{"pk": k} for k in keys[start : start + BATCH_GET_LIMIT]]}}
            for _ in range(MAX_UNPROCESSED_ROUNDS):
                response = self.resource.batch_get_item(RequestItems=request)
                for row in response.get("Responses", {}).get(self.table_name, []):
                    found[row["pk"]] = row
                request = response.get("UnprocessedKeys") or {}
                if not request.get(self.table_name):
                    break
        return found

    def put_new(self, item: dict) -> bool:
        """Insert only if the key is absent. Returns False when it already exists."""
        try:
            self.table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def mark_sent(self, key: str, at: int) -> None:
        self.table.update_item(
            Key={"pk": key},
            UpdateExpression="SET notify_state = :state, notified_at = :at",
            ExpressionAttributeValues={":state": "sent", ":at": at},
        )

    def bump_attempt(self, key: str) -> int:
        response = self.table.update_item(
            Key={"pk": key},
            UpdateExpression="SET notify_attempts = if_not_exists(notify_attempts, :zero) + :one",
            ExpressionAttributeValues={":zero": 0, ":one": 1},
            ReturnValues="UPDATED_NEW",
        )
        return int(response["Attributes"]["notify_attempts"])

    def mark_failed(self, key: str) -> None:
        self.table.update_item(
            Key={"pk": key},
            UpdateExpression="SET notify_state = :state",
            ExpressionAttributeValues={":state": "failed"},
        )
