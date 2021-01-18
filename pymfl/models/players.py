from .player import Player


class Players:
    def __init__(self):
        self._players = {}

    def __repr__(self):
        return self._players.__repr__()

    def add_player(self, player: Player):
        self._players[player.player_id] = player

        return self._players
