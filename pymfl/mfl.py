import requests
import json
import os
from .models.franchise import Franchise
from .models.league_franchises import LeagueFranchises
from .models.player import Player
from .models.players import Players


class MFL:
    _base_url = "https://api.myfantasyleague.com/"

    def __init__(
        self, username: str, password: str, league_id: int, year: int, json: bool = True
    ):

        self._year = year
        self._username = username
        self._password = password
        self._league_id = league_id
        self._json = "1" if json else "0"
        self._api = requests.Session()
        self._base_url += f"{self._year}/export?"

    def login(self):
        login = self._get_request(
            "login",
            ["USERNAME", "PASSWORD"],
            USERNAME=self._username,
            PASSWORD=self._password,
        )

        return login.status_code

    def league_info(self):
        league_info = self._get_request("league", ["L"], L=self._league_id)

        return league_info

    def franchises(self):
        """Returns a LeagueFranchises object containing all of the franchises for the MFL league"""
        league_info = self.league_info()
        raw_list_of_franchises = league_info["league"]["franchises"]["franchise"]

        league_franchises = LeagueFranchises()

        for franchise_raw in raw_list_of_franchises:
            franchise = Franchise(franchise_raw)
            league_franchises.add_franchise(franchise)

        return league_franchises

    def trades(self, number_of_days: str = ""):

        return self.transactions(number_of_days, "TRADE")

    def waivers(self, number_of_days: str = ""):

        return self.transactions(number_of_days, "WAIVER")

    def live_scores(self):
        transactions = self._get_request("liveScoring", ["L"], L=self._league_id)

        return transactions["liveScoring"]["matchup"]

    def transactions(self, number_of_days: str, transaction_type: str = "*"):
        """Returns list of completed transactions over previous designated number of days"""

        transactions = self._get_request(
            "transactions",
            ["L", "DAYS", "TRANS_TYPE"],
            L=self._league_id,
            DAYS=number_of_days,
            TRANS_TYPE=transaction_type,
        )

        return transactions["transactions"]["transaction"]

    def injuries(self, week: str = ""):
        injuries = self._get_request("injuries", ["W"], W=week)

        injuries_json = json.loads(injuries.content)
        raw_list_of_injuries = injuries_json["injuries"]["injury"]

        injured_players = Players()

        for player_injury in raw_list_of_injuries:
            player = Player(player_injury)
            injured_players.add_player(player)

        return injured_players

    def current_week_injuries(self):
        return self.injuries()

    def rosters(self):
        rosters = self._get_request("rosters", ["L"], L=self._league_id)

        return rosters.content

    def players(self):
        players = self._get_request("players", ["L"], L=self._league_id)

        return players["players"]["player"]

    def _build_request(self, endpoint: str, required_args: list(), kwargs):
        """Creates url to use for request given the endpoint name, required arguments, and keyword arguments"""
        passed_args = kwargs.keys()
        self._check_required_arguments_passed(required_args, passed_args)

        request_string = self._format_request(endpoint, kwargs)

        return request_string

    def _check_required_arguments_passed(self, required_args: list(), passed_args):
        for req_arg in required_args:
            if req_arg not in passed_args:
                raise Exception("Missing argument: " + req_arg)

    def _format_request(self, endpoint: str, passed_args):
        request_string = self._base_url + "TYPE=" + endpoint

        for arg in passed_args:
            request_string += f"&{arg}={passed_args[arg]}"

        request_string += "&JSON=" + self._json

        return request_string

    def _get_request(self, endpoint, required_args, **kwargs):
        request = self._build_request(endpoint, required_args, kwargs)

        response = self._api.get(request)

        if response.status_code != 200:
            raise Exception(response)

        response_json = json.loads(response.content)

        return response_json
