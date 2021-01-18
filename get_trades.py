import json
import os
import boto3
import datetime
from pymfl.mfl import MFL


def handler(event, context):
    mfl = MFL(
        os.getenv("MFL_USERNAME"),
        os.getenv("MFL_PASSWORD"),
        os.getenv("MFL_LEAGUEID"),
        os.getenv("MFL_API_YEAR"),
    )

    trades = mfl.trades()

    test_object = {
        "timestamp": "test",
        "comments": "test",
        "franchise": "0008",
        "franchise2": "0007",
        "franchise1_gave_up": "DP_0_1",
        "franchise2_gave_up": "14136,13631,FP_0004_2022_3,",
    }

    trades.append(test_object)

    new_trades_messages = store_trades_if_not_exist(trades)

    body = {"trades": new_trades_messages}

    send_sqs_messages(new_trades_messages)

    response = {"statusCode": 200, "body": body}

    return response


def get_trades_messages(trades):

    trades_messages = []

    for trade in trades:
        trade_message = create_trade_message(trade)
        trades_messages.append(trade_message)

    return trades_messages


def create_trade_message(trade):
    formatted_trade = format_trade(trade)

    message = format_trade_message(
        formatted_trade["franchise1_name"],
        formatted_trade["franchise2_name"],
        formatted_trade["franchise1_assets"],
        formatted_trade["franchise2_assets"],
    )

    return message


def format_trade(trade):

    formatted_trade = create_trade_object(trade)

    return formatted_trade


def create_trade_object(trade):
    timestamp = trade["timestamp"]
    comments = trade["comments"]
    franchise1_id = trade["franchise"]
    franchise2_id = trade["franchise2"]
    franchise1_gave_up = trade["franchise1_gave_up"]
    franchise2_gave_up = trade["franchise2_gave_up"]

    # get franchise names from ids
    franchise1_name = get_field_from_id("franchises", "name", franchise1_id)
    franchise2_name = get_field_from_id("franchises", "name", franchise2_id)

    # get asset names from gave up statement
    franchise1_assets = get_assets(franchise1_gave_up)
    franchise2_assets = get_assets(franchise2_gave_up)

    trade_object = {
        "timestamp": timestamp,
        "comments": comments,
        "franchise1_id": franchise1_id,
        "franchise2_id": franchise2_id,
        "franchise1_gave_up": franchise1_gave_up,
        "franchise2_gave_up": franchise2_gave_up,
        "franchise1_name": franchise1_name,
        "franchise2_name": franchise2_name,
        "franchise1_assets": franchise1_assets,
        "franchise2_assets": franchise2_assets,
    }

    return trade_object


def get_assets(assets):

    formatted_assets = []
    message = ""

    for trade_item in assets.split(","):

        if is_blind_bid_dollars(trade_item):

            message = create_blind_bid_message(trade_item)
            formatted_assets.append(message)

        elif is_future_pick(trade_item):

            message = create_future_pick_message(trade_item)
            formatted_assets.append(message)

        elif is_current_pick(trade_item):

            message = create_current_pick_message(trade_item)
            formatted_assets.append(message)

        elif trade_item is not "":
            try:
                player_name = get_field_from_id("players", "name", trade_item)
                player_position = get_field_from_id("players", "position", trade_item)
                player_team = get_field_from_id("players", "team", trade_item)
                player_string = f"{player_name}, {player_team} {player_position}"
                formatted_assets.append(player_string)
            except:
                raise Exception(f"Threw error for: {trade_item}")

    return formatted_assets


def get_field_from_id(table_name, field, primary_id):

    dynamodb = boto3.resource("dynamodb")

    table = dynamodb.Table(table_name)

    item = table.get_item(Key={"id": primary_id})

    name = item["Item"][field]

    return name


def format_trade_message(
    franchise1_name, franchise2_name, franchise1_assets, franchise2_assets
):

    assets1_str = format_asset_string(franchise1_assets)
    assets2_str = format_asset_string(franchise2_assets)

    message = (
        "🚨TRADE COMPLETED🚨\n"
        "\n"
        f"{franchise1_name} GIVES UP:\n"
        f"{assets1_str}"
        "\n"
        f"{franchise2_name} GIVES UP:\n"
        f"{assets2_str}"
    )

    return message


def format_asset_string(assets):
    indent = "- "
    assets_str = ""

    for asset in assets:
        assets_str += indent + asset + "\n"

    return assets_str


def is_blind_bid_dollars(trade_item):

    return trade_item[:2] == "BB"


def is_future_pick(trade_item):

    return trade_item[:2] == "FP"


def is_current_pick(trade_item):

    return trade_item[:2] == "DP"


def create_blind_bid_message(trade_item):

    dollars = trade_item.split("_")[1]

    return f"${dollars}"


def create_future_pick_message(trade_item):

    split = trade_item.split("_")

    franchise_id = split[1]
    year = split[2]
    rd = split[3]

    franchise_name = get_field_from_id("franchises", "name", franchise_id)

    return f"{franchise_name} {year} Round {rd} Draft Pick"


def create_current_pick_message(trade_item):

    split = trade_item.split("_")

    year = datetime.date.today().year
    rd = int(split[1]) + 1
    pick = int(split[2])

    return f"{year} Round {rd} Pick {pick}"


def store_trades_if_not_exist(trades):
    """Stores new trades that did not previously exist in db, returns trades that were stored"""

    new_trades = []

    for trade in trades:
        trade_obj = create_trade_object(trade)
        if is_new_trade(trade_obj):
            store_trade_in_dynamodb(trade_obj)
            trade_message = format_trade_message(
                trade_obj["franchise1_name"],
                trade_obj["franchise2_name"],
                trade_obj["franchise1_assets"],
                trade_obj["franchise2_assets"],
            )
            new_trades.append(trade_message)

    return new_trades


def is_new_trade(trade):
    return not exists_in_dynamodb("timestamp", trade["timestamp"], "trades")


def exists_in_dynamodb(key_name, key_value, table_name):

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    exists = True

    try:
        item = table.get_item(Key={key_name: key_value})
        item = item["Item"]
    except KeyError:
        exists = False

    return exists


def store_trade_in_dynamodb(trade_obj):

    dynamodb = boto3.resource("dynamodb")

    trades_table = dynamodb.Table("trades")

    trades_table.update_item(
        Key={"timestamp": trade_obj["timestamp"]},
        ExpressionAttributeNames={
            "#C": "comments",
            "#FIDO": "franchise1_id",
            "#FIDT": "franchise2_id",
            "#FGUO": "franchise1_gave_up",
            "#FGUT": "franchise2_gave_up",
            "#FNO": "franchise1_name",
            "#FNT": "franchise2_name",
            "#FAO": "franchise1_assets",
            "#FAT": "franchise2_assets",
        },
        ExpressionAttributeValues={
            ":c": trade_obj["comments"],
            ":fido": trade_obj["franchise1_id"],
            ":fidt": trade_obj["franchise2_id"],
            ":fguo": trade_obj["franchise1_gave_up"],
            ":fgut": trade_obj["franchise2_gave_up"],
            ":fno": trade_obj["franchise1_name"],
            ":fnt": trade_obj["franchise2_name"],
            ":fao": trade_obj["franchise1_assets"],
            ":fat": trade_obj["franchise2_assets"],
        },
        UpdateExpression="SET #C=:c, #FIDO=:fido, #FIDT=:fidt, #FGUO=:fguo, #FGUT=:fgut, #FNO=:fno, #FNT=:fnt, #FAO=:fao, #FAT=:fat",
    )


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
