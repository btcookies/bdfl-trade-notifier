import json
import os
import time
import boto3
from pymfl.mfl import MFL


def handler(event, context):
    mfl = MFL(
        os.getenv("MFL_USERNAME"),
        os.getenv("MFL_PASSWORD"),
        os.getenv("MFL_LEAGUEID"),
        os.getenv("MFL_API_YEAR"),
    )

    waivers = mfl.waivers()

    # TODO: make tests for function, move to separate file
    # test_object = {
    #     'timestamp': str(int(time.time())),
    #     'franchise': '0008',
    #     'transaction': '8670,|1.00|13988,',
    #     'type': 'BBID_WAIVER'
    # }

    # test2_object = {
    #     'timestamp': '0000000002',
    #     'franchise': '0002',
    #     'transaction': '8670,|2.00|13988,',
    #     'type': 'BBID_WAIVER'
    # }

    # test3_object = {
    #     'timestamp': '0000000003',
    #     'franchise': '0011',
    #     'transaction': '8670,|3.00|',
    #     'type': 'BBID_WAIVER'
    # }

    # test4_object = {
    #     'timestamp': '0000000004',
    #     'franchise': '0008',
    #     'transaction': '8670,|4.00|13988,',
    #     'type': 'BBID_WAIVER'
    # }

    # test5_object = {
    #     'timestamp': '0000000005',
    #     'franchise': '0002',
    #     'transaction': '8670,|5.00|13988,',
    #     'type': 'BBID_WAIVER'
    # }

    # test6_object = {
    #     'timestamp': '0000000006',
    #     'franchise': '0011',
    #     'transaction': '8670,|6.00|',
    #     'type': 'BBID_WAIVER'
    # }

    # test7_object = {
    #     'timestamp': '0000000007',
    #     'franchise': '0011',
    #     'transaction': '8670,|7.00|',
    #     'type': 'BBID_WAIVER'
    # }

    # waivers.append(test_object)
    # waivers.append(test2_object)
    # waivers.append(test3_object)
    # waivers.append(test4_object)
    # waivers.append(test5_object)
    # waivers.append(test6_object)
    # waivers.append(test7_object)

    new_waivers_messages = store_waivers_if_not_exist(waivers)

    body = {"waivers": new_waivers_messages}

    send_sqs_messages(new_waivers_messages)

    response = {"statusCode": 200, "body": body}

    return response


def store_waivers_if_not_exist(waivers):
    """
    Stores new waivers that did not previously exist in db, returns waivers that were stored
    waiver_object = {
        'key': key,
        'timestamp': timestamp,
        'franchise_id': franchise_id,
        'raw_transaction': transaction,
        'formatted_transaction': formatted_transaction,
        'franchise_name':  franchise_name,
        'type': t_type
    }
    """
    base_string = "✅WAIVER CLAIMS COMPLETED✅\n"
    new_waivers = [base_string]

    for waiver in waivers:
        waiver_obj = create_waiver_object(waiver)
        if is_new_waiver(waiver_obj):
            store_waiver_in_dynamodb(waiver_obj)
            waiver_message = format_waiver_message(
                waiver_obj["franchise_name"], waiver_obj["formatted_transaction"]
            )
            new_waivers.append(waiver_message)

    new_waivers_message = []
    if len(new_waivers) > 1:
        new_waivers_message = ["\n".join(new_waivers)]

    return new_waivers_message


def create_waiver_object(waiver):
    timestamp = waiver["timestamp"]
    franchise_id = waiver["franchise"]
    transaction = waiver["transaction"]
    t_type = waiver["type"]

    # get franchise names from ids
    franchise_name = get_field_from_id("franchises", "name", franchise_id)

    # get asset names from gave up statement
    formatted_transaction = format_transaction(transaction)
    player_added_name = formatted_transaction[1]
    key = create_waivers_table_key(timestamp, player_added_name)
    waiver_object = {
        "key": key,
        "timestamp": timestamp,
        "franchise_id": franchise_id,
        "raw_transaction": transaction,
        "formatted_transaction": formatted_transaction,
        "franchise_name": franchise_name,
        "type": t_type,
    }

    return waiver_object


def get_field_from_id(table_name, field, primary_id):

    dynamodb = boto3.resource("dynamodb")

    table = dynamodb.Table(table_name)

    item = table.get_item(Key={"id": primary_id})

    name = item["Item"][field]

    return name


def format_transaction(transaction):

    split_transaction = transaction.split(",")

    player_added_id = split_transaction[0]
    player_added_name = get_field_from_id("players", "name", player_added_id)
    player_added_team = get_field_from_id("players", "team", player_added_id)
    player_added_position = get_field_from_id("players", "position", player_added_id)
    player_added_string = (
        f"{player_added_name}, {player_added_team} {player_added_position}"
    )

    bid_and_drop = split_transaction[1].split("|")
    bid = "$" + bid_and_drop[1]

    player_dropped_id = bid_and_drop[2] if len(bid_and_drop) == 3 else None
    player_dropped_string = None
    if player_dropped_id:
        player_dropped_name = get_field_from_id("players", "name", player_dropped_id)
        player_dropped_team = get_field_from_id("players", "team", player_dropped_id)
        player_dropped_position = get_field_from_id(
            "players", "position", player_dropped_id
        )
        player_dropped_string = (
            f"{player_dropped_name}, {player_dropped_team} {player_dropped_position}"
        )

    formatted_transaction = [bid, player_added_string, player_dropped_string]

    return formatted_transaction


def create_waivers_table_key(timestamp, player_added_name):
    return timestamp + "-" + player_added_name.replace(" ", "-").replace(",", "")


def is_new_waiver(waiver):
    return not is_in_dynamodb("key", waiver["key"], "waivers") and is_timestamp_recent(
        int(waiver["timestamp"])
    )


def is_in_dynamodb(key_name, key_value, table_name):

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    exists = True

    try:
        item = table.get_item(Key={key_name: key_value})
        item = item["Item"]
    except KeyError:
        exists = False

    return exists


def is_timestamp_recent(waiver_timestamp):
    """
    86400 seconds in a day, add 900 for 15 min max lambda run time to account for waivers that occurred during
    previous day's lambda invocation. Timestamps that are less than this recency threshold older than the current
    timestamp are "recent" otherwise the transaction is old and we do not report it
    """
    recency_threshold_in_secs = 87300
    current_timestamp = int(time.time())

    return (current_timestamp - waiver_timestamp) < recency_threshold_in_secs


def store_waiver_in_dynamodb(waiver_obj):
    """
       waiver_object = {
        'key': key,
        'franchise_id': franchise_id,
        'raw_transaction': transaction,
        'formatted_transaction': formatted_transaction,
        'franchise_name':  franchise_name,
        'type': t_type
    }
    """

    dynamodb = boto3.resource("dynamodb")

    waivers_table = dynamodb.Table("waivers")

    waivers_table.update_item(
        Key={"key": waiver_obj["key"]},
        ExpressionAttributeNames={
            "#FID": "franchise_id",
            "#RT": "raw_transaction",
            "#FT": "formatted_transaction",
            "#FN": "franchise_name",
            "#T": "type",
            "#TS": "timestamp",
        },
        ExpressionAttributeValues={
            ":fid": waiver_obj["franchise_id"],
            ":rt": waiver_obj["raw_transaction"],
            ":ft": waiver_obj["formatted_transaction"],
            ":fn": waiver_obj["franchise_name"],
            ":t": waiver_obj["type"],
            ":ts": waiver_obj["timestamp"],
        },
        UpdateExpression="SET #FID=:fid, #RT=:rt, #FT=:ft, #FN=:fn, #T=:t, #TS=:ts",
    )


def format_waiver_message(franchise_name, transaction):

    transaction_str = format_add_drop_string(transaction)

    message = f"{franchise_name} {transaction_str}\n"

    return message


def format_add_drop_string(transaction):
    """
    transaction = [bid_amt, player_added_name, player_dropped_name]
    where player_dropped_name is None if no player was dropped
    """
    bid_amt = transaction[0]
    player_added_name = transaction[1]
    player_dropped_name = transaction[2]

    message = f"won {player_added_name} with a {bid_amt} bid"

    if player_dropped_name:
        message += f" and dropped {player_dropped_name}"

    return message


def send_sqs_messages(messages):

    for message in messages:
        send_sqs_message("BDFLMessageQueue", message)


def send_sqs_message(queue_name, message):
    sqs_client = boto3.client("sqs")
    sqs_queue_url = sqs_client.get_queue_url(QueueName=queue_name)["QueueUrl"]

    try:
        msg = sqs_client.send_message(QueueUrl=sqs_queue_url, MessageBody=message)
    except Exception as e:
        print(e)
        return None

    return msg
