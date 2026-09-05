import os

# moto needs credentials and a region before boto3 creates any client.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

import boto3
import pytest
from moto import mock_aws

TABLE_NAME = "bdfl-notifier-transactions"


@pytest.fixture
def dynamodb_table():
    """A moto-backed table with the same key schema as template.yaml."""
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        table = resource.create_table(
            TableName=TABLE_NAME,
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )
        table.wait_until_exists()
        yield resource, TABLE_NAME


@pytest.fixture(autouse=True)
def restore_logger_levels():
    """build_poller reconfigures shared loggers; put them back so tests stay order-independent."""
    import logging

    names = ("", "bdfl", "botocore", "boto3", "urllib3")
    saved = {name: logging.getLogger(name).level for name in names}
    yield
    for name, level in saved.items():
        logging.getLogger(name).setLevel(level)
