import json
import requests


class GroupMe:
    _base_url = f"https://api.groupme.com/v3/"
    CHARACTER_LIMIT = 450

    def __init__(self, api_key: str):

        self._api_key = api_key
        self._api = requests.Session()

    def send_message(self, bot_id, message):
        url = self._base_url + "bots/post"
        body = {"bot_id": bot_id, "text": message}

        return self._api.post(url, json.dumps(body))

    def format_bdfl_messages_for_character_limit(self, messages):
        """
        Takes in array of messages list(str) and returns list of messages
        that comply with CHARACTER_LIMIT of GroupMe messages
        """
        messages_to_send = []
        limited_message = ""

        for message in messages:
            for i in message.split("\n"):
                if len(limited_message) + len(i) < self.CHARACTER_LIMIT:
                    limited_message += i + "\n"
                else:
                    messages_to_send.append(limited_message[:-1])
                    limited_message = i + "\n"

            if len(message) > 0:
                messages_to_send.append(limited_message[:-1])

        return messages_to_send
