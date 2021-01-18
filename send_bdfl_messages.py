import json
import os
from pymfl.mfl import MFL
from groupme.groupme import GroupMe


def handler(event, context):

    messages = []
    for message_obj in event["Records"]:
        messages.append(message_obj["body"])

    groupme = GroupMe(os.getenv("GROUPME_API_KEY"))

    messages_to_send = groupme.format_bdfl_messages_for_character_limit(messages)

    sent_messages = send_messages(messages_to_send)

    print("number of sent messages: ", len(sent_messages))
    print("sent messages: ", sent_messages)

    response = {"statusCode": 200, "body": sent_messages}

    return response


def send_messages(messages):

    sent_messages = []
    groupme = GroupMe(os.getenv("GROUPME_API_KEY"))
    bot_id = os.getenv("GROUPME_BOT_ID")

    for message in messages:

        print(groupme.send_message(bot_id, message))

        sent_messages.append(message)

    return sent_messages
