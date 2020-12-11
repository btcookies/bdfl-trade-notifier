import requests

class GroupMe:
    _base_url = f'https://api.groupme.com/v3/'

    def __init__(self, api_key: str):

        self._api_key = api_key
        self._api = requests.Session()

    def send_message(self, bot_id, message):
        url = self._base_url + 'bots/post'
        body = {
            'bot_id': bot_id,
            'text': message
        }

        return self._api.post(url, body)