from datetime import UTC, datetime

import pytest
import responses

from bdfl.mfl import BASE_URL, LeagueNotFound, MflClient, MflError, MflThrottled

LEAGUE_ID = "65522"
NOW = datetime(2026, 9, 4, tzinfo=UTC)


def league_body(year, years, franchises=None):
    return {
        "league": {
            "id": LEAGUE_ID,
            "name": "BDFL",
            "history": {"league": [{"year": str(y), "url": f"https://x/{y}"} for y in years]},
            "franchises": {
                "franchise": franchises
                or [{"id": "0001", "name": "The Youth Academy"}, {"id": "0002", "name": "A.J. Mudbone"}]
            },
        }
    }


def make_client(**kwargs):
    defaults = {"league_id": LEAGUE_ID, "user_agent": "test-agent", "sleep": lambda s: None}
    return MflClient(**{**defaults, **kwargs})


@responses.activate
def test_detect_league_uses_current_year_when_it_exists():
    responses.get(
        f"{BASE_URL}/2026/export", json=league_body(2026, [2026, 2016, 2025]), match=[
            responses.matchers.query_param_matcher({"TYPE": "league", "L": LEAGUE_ID, "JSON": "1"})
        ]
    )
    league = make_client().detect_league(NOW)
    assert league.year == 2026
    assert league.name == "BDFL"
    assert league.franchises == {"0001": "The Youth Academy", "0002": "A.J. Mudbone"}
    assert responses.calls[0].request.headers["User-Agent"] == "test-agent"


@responses.activate
def test_detect_league_falls_back_to_prior_year_on_404_and_reads_newer_year_from_history():
    responses.get(f"{BASE_URL}/2026/export", status=404, body="<H1>Not Found</H1>")
    responses.get(f"{BASE_URL}/2025/export", json=league_body(2025, [2025, 2024]))
    assert make_client().detect_league(NOW).year == 2025

    responses.reset()
    responses.get(f"{BASE_URL}/2026/export", json={"error": {"$t": "Invalid league ID"}})
    responses.get(f"{BASE_URL}/2025/export", json=league_body(2025, [2025, 2026]))
    responses.get(f"{BASE_URL}/2026/export", json=league_body(2026, [2025, 2026],
                  franchises=[{"id": "0001", "name": "Renamed"}]))
    league = make_client().detect_league(NOW)
    assert league.year == 2026
    assert league.franchises == {"0001": "Renamed"}


@responses.activate
def test_detect_league_handles_single_history_entry_dict():
    body = league_body(2026, [2026])
    body["league"]["history"]["league"] = body["league"]["history"]["league"][0]
    responses.get(f"{BASE_URL}/2026/export", json=body)
    assert make_client().detect_league(NOW).year == 2026


@responses.activate
def test_detect_league_raises_when_no_year_exists():
    responses.get(f"{BASE_URL}/2026/export", status=404)
    responses.get(f"{BASE_URL}/2025/export", status=404)
    with pytest.raises(LeagueNotFound):
        make_client().detect_league(NOW)


@responses.activate
def test_transactions_passes_types_and_days_and_returns_payload():
    payload = {"transactions": {"transaction": [{"type": "TRADE"}]}}
    responses.get(f"{BASE_URL}/2026/export", json=payload, match=[
        responses.matchers.query_param_matcher({
            "TYPE": "transactions", "L": LEAGUE_ID, "JSON": "1",
            "TRANS_TYPE": "TRADE,BBID_WAIVER", "DAYS": "1",
        })
    ])
    assert make_client().transactions(2026) == payload


@responses.activate
def test_transactions_raises_on_error_body_and_bad_status():
    responses.get(f"{BASE_URL}/2026/export", json={"error": {"$t": "nope"}})
    with pytest.raises(MflError, match="nope"):
        make_client().transactions(2026)
    responses.reset()
    responses.get(f"{BASE_URL}/2026/export", status=500)
    with pytest.raises(MflError, match="500"):
        make_client().transactions(2026)
    responses.reset()
    responses.get(f"{BASE_URL}/2026/export", status=404)
    with pytest.raises(MflError):
        make_client().transactions(2026)


@responses.activate
def test_throttled_raises_specific_error_and_does_not_retry():
    responses.get(f"{BASE_URL}/2026/export", status=429)
    with pytest.raises(MflThrottled):
        make_client().transactions(2026)
    assert len(responses.calls) == 1


@responses.activate
def test_players_returns_map_and_skips_request_for_no_ids():
    responses.get(f"{BASE_URL}/2026/export", json={"players": {"player": [
        {"id": "13299", "name": "Kittle, George", "team": "SFO", "position": "TE"},
        {"id": "17463", "name": "Simpson, Ty", "position": "QB", "status": "R"},
    ]}}, match=[responses.matchers.query_param_matcher({
        "TYPE": "players", "L": LEAGUE_ID, "JSON": "1", "PLAYERS": "13299,17463",
    })])
    players = make_client().players(2026, ["17463", "13299", "13299"])
    assert players["13299"].name == "Kittle, George"
    assert players["13299"].team == "SFO"
    assert players["17463"].team == ""
    assert make_client().players(2026, []) == {}
    assert len(responses.calls) == 1


@responses.activate
def test_requests_are_paced_one_second_apart():
    responses.get(f"{BASE_URL}/2026/export", json=league_body(2026, [2026]))
    responses.get(f"{BASE_URL}/2026/export", json={"transactions": {}})
    slept = []
    # clock() is read once after each request finishes and once before each paced request:
    # finish of request 1 (100.0), pace check before request 2 (100.3), finish of request 2.
    ticks = iter([100.0, 100.3, 100.3])
    client = make_client(sleep=slept.append, clock=lambda: next(ticks))
    client.detect_league(NOW)
    client.transactions(2026)
    assert slept == [pytest.approx(0.7)]


@responses.activate
def test_non_json_body_raises_mfl_error():
    responses.get(f"{BASE_URL}/2026/export", body="<html>oops</html>", status=200)
    with pytest.raises(MflError, match="JSON"):
        make_client().transactions(2026)
