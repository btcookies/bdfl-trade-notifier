import json
import os
from pymfl.mfl import MFL
from groupme.groupme import GroupMe


def handler(event, context):

    messages = event['Records']

    sent_messages = send_messages(messages)

    print('number of sent messages: ', len(sent_messages))
    print('sent messages: ', sent_messages)

    response = {
        "statusCode": 200,
        "body": sent_messages
    }

    return response

def send_messages(messages):

    sent_messages = []
    groupme = GroupMe(os.getenv('GROUPME_API_KEY'))
    bot_id = os.getenv('GROUPME_BOT_ID')

    for message in messages:

        message_text = message['body']

        print(groupme.send_message(bot_id, message_text))

        sent_messages.append(message_text)
    
    return sent_messages
