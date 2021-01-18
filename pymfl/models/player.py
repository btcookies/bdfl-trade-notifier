class Player:
    """Struct representing player object returned from MFL"""

    def __init__(self, player_json):
        self.player_id = player_json["id"]
        self.injury_status = player_json["status"]
        self.roster_status = self.get_roster

    def __repr__(self):
        id_str = f"player id: {self.player_id}"
        status_str = f"injury status: {self.injury_status}"

        return "{" + ",\n\t".join([id_str, status_str]) + "}"

    def __str__(self):
        return self.__repr__()
