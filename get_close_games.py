import json
import os
import boto3
from pymfl.mfl import MFL


def handler(event, context):
    mfl = MFL(
        os.getenv("MFL_USERNAME"),
        os.getenv("MFL_PASSWORD"),
        os.getenv("MFL_LEAGUEID"),
        os.getenv("MFL_API_YEAR"),
    )

    live_scores = mfl.live_scores()

    close_games_message = close_games(live_scores)

    body = {"close_games": close_games_message}

    send_sqs_messages(close_games_message)

    response = {"statusCode": 200, "body": body}

    return response


def close_games(live_scores):

    base_string = "👀CLOSE GAMES👀\n"
    close_games = [base_string]

    for matchup in live_scores:

        matchup_obj = create_matchup_object(matchup)

        if is_close_game(matchup_obj):
            message = create_close_game_message(matchup_obj)
            close_games.append(message)

    close_games_message = []
    if len(close_games) > 1:
        close_games_message = ["\n".join(close_games)]

    return close_games_message


def create_matchup_object(matchup):
    franchises = matchup["franchise"]

    franchise1_id = franchises[0]["id"]
    franchise1_score = franchises[0]["score"]
    franchise1_num_players_left = franchises[0]["playersYetToPlay"]

    franchise2_id = franchises[1]["id"]
    franchise2_score = franchises[1]["score"]
    franchise2_num_players_left = franchises[1]["playersYetToPlay"]

    franchise1_name = get_field_from_id("franchises", "name", franchise1_id)
    franchise2_name = get_field_from_id("franchises", "name", franchise2_id)

    matchup_obj = {
        "franchise1_id": franchise1_id,
        "franchise1_name": franchise1_name,
        "franchise1_score": franchise1_score,
        "franchise1_num_players_left": franchise1_num_players_left,
        "franchise2_id": franchise2_id,
        "franchise2_name": franchise2_name,
        "franchise2_score": franchise2_score,
        "franchise2_num_players_left": franchise2_num_players_left,
    }

    return matchup_obj


def is_close_game(matchup_obj):
    return (
        abs(
            float(matchup_obj["franchise1_score"])
            - float(matchup_obj["franchise2_score"])
        )
        <= 10
    )


def create_close_game_message(matchup_obj):
    """
    matchup_obj = {
        'franchise1_id': franchise1_id,
        'franchise1_name': franchise1_name,
        'franchise1_score': franchise1_score,
        'franchise1_num_players_left': franchise1_num_players_left,
        'franchise2_id': franchise2_id,
        'franchise2_name': franchise2_name,
        'franchise2_score': franchise2_score,
        'franchise2_num_players_left': franchise2_num_players_left
    }
    """

    franchise1_name = matchup_obj["franchise1_name"]
    franchise1_num_players_left = matchup_obj["franchise1_num_players_left"]
    franchise1_score = matchup_obj["franchise1_score"]

    franchise2_name = matchup_obj["franchise2_name"]
    franchise2_num_players_left = matchup_obj["franchise2_num_players_left"]
    franchise2_score = matchup_obj["franchise2_score"]

    status_string = "BEATING" if franchise1_score > franchise2_score else "LOSING TO"

    message = (
        f"{franchise1_name} {status_string} {franchise2_name} {franchise1_score} - {franchise2_score}\n"
        f"- {franchise1_name} players left: {franchise1_num_players_left}\n"
        f"- {franchise2_name} players left: {franchise2_num_players_left}\n"
    )

    return message


def get_field_from_id(table_name, field, primary_id):

    dynamodb = boto3.resource("dynamodb")

    table = dynamodb.Table(table_name)

    item = table.get_item(Key={"id": primary_id})

    name = item["Item"][field]

    return name


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
