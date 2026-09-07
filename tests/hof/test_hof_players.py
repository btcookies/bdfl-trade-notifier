import json

from hof.model.players import UNKNOWN_POSITION, PlayerInfo, parse_players


def test_parses_the_2020_players_snapshot(fixtures_dir):
    body = json.loads((fixtures_dir / "raw" / "2020" / "players.json").read_text())
    players = parse_players(body)
    assert len(players) > 300
    ryan = players["9099"]
    assert ryan == PlayerInfo(id="9099", name="Matt Ryan", position="QB", team="ATL")


def test_parse_handles_single_player_dict_and_missing_fields():
    body = {"players": {"player": {"id": " 7 ", "name": "Doe, Jane"}}}
    assert parse_players(body) == {"7": PlayerInfo("7", "Jane Doe", UNKNOWN_POSITION, "")}


def test_unknown_player_placeholder():
    unknown = PlayerInfo.unknown("42")
    assert unknown.name == "Unknown player (#42)"
    assert unknown.position == UNKNOWN_POSITION
