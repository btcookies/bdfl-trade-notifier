from datetime import UTC, datetime

import pytest
import requests
import responses

from bdfl.mfl import (
    BASE_URL,
    LeagueNotFound,
    MflClient,
    MflError,
    MflNotFound,
    MflThrottled,
    RequestPacer,
)

LEAGUE_ID = "65522"
NOW = datetime(2026, 9, 4, tzinfo=UTC)


class FakeClock:
    def __init__(self, start=100.0):
        self.now = start

    def __call__(self):
        return self.now


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
def test_detect_league_falls_back_to_prior_year_and_ignores_history():
    responses.get(f"{BASE_URL}/2026/export", status=404, body="<H1>Not Found</H1>")
    responses.get(f"{BASE_URL}/2025/export", json=league_body(2025, [2025, 2026, 2027]))
    league = make_client().detect_league(NOW)
    assert league.year == 2025
    assert len(responses.calls) == 2

    responses.reset()
    responses.get(f"{BASE_URL}/2026/export", json={"error": {"$t": "Invalid league ID"}})
    responses.get(f"{BASE_URL}/2025/export", json=league_body(2025, [2025]))
    assert make_client().detect_league(NOW).year == 2025
    assert len(responses.calls) == 2


@responses.activate
def test_detect_league_prefers_current_year_even_if_history_lists_a_future_year():
    responses.get(f"{BASE_URL}/2026/export", json=league_body(2026, [2026, 2027]))
    league = make_client().detect_league(NOW)
    assert league.year == 2026
    assert len(responses.calls) == 1


@responses.activate
def test_detect_league_handles_single_franchise_dict():
    body = league_body(2026, [2026])
    body["league"]["franchises"]["franchise"] = {"id": "0001", "name": "Solo"}
    responses.get(f"{BASE_URL}/2026/export", json=body)
    league = make_client().detect_league(NOW)
    assert league.year == 2026
    assert league.franchises == {"0001": "Solo"}


@responses.activate
def test_non_object_json_body_raises_mfl_error():
    responses.get(f"{BASE_URL}/2026/export", body="null", content_type="application/json")
    with pytest.raises(MflError, match="non-object"):
        make_client().transactions(2026)
    responses.reset()
    responses.get(f"{BASE_URL}/2026/export", json=[1, 2])
    with pytest.raises(MflError, match="non-object"):
        make_client().league(2026)


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
def test_players_strips_whitespace_from_fields():
    responses.get(f"{BASE_URL}/2026/export", json={"players": {"player": [
        {"id": "13299", "name": " Kittle, George ", "team": " SFO ", "position": " TE "},
    ]}})
    player = make_client().players(2026, ["13299"])["13299"]
    assert (player.name, player.team, player.position) == ("Kittle, George", "SFO", "TE")


@responses.activate
def test_requests_are_paced_one_second_apart():
    responses.get(f"{BASE_URL}/2026/export", json=league_body(2026, [2026]))
    responses.get(f"{BASE_URL}/2026/export", json={"transactions": {}})
    slept = []
    clock = FakeClock()
    client = make_client(sleep=slept.append, clock=clock)
    client.detect_league(NOW)
    clock.now = 100.3
    client.transactions(2026)
    assert slept == [pytest.approx(0.7)]


@responses.activate
def test_non_json_body_raises_mfl_error():
    responses.get(f"{BASE_URL}/2026/export", body="<html>oops</html>", status=200)
    with pytest.raises(MflError, match="JSON"):
        make_client().transactions(2026)


@responses.activate
def test_detect_league_propagates_throttle_and_server_errors():
    responses.get(f"{BASE_URL}/2026/export", status=429)
    with pytest.raises(MflThrottled):
        make_client().detect_league(NOW)
    assert len(responses.calls) == 1
    responses.reset()
    responses.get(f"{BASE_URL}/2026/export", status=500)
    with pytest.raises(MflError) as info:
        make_client().detect_league(NOW)
    assert not isinstance(info.value, MflNotFound)
    assert len(responses.calls) == 1


@responses.activate
def test_a_transient_connection_error_is_retried_and_recovered():
    """MFL's server occasionally resets a pooled keep-alive connection right around our
    pacing gap; that isn't a rate-limit signal, so it's worth retrying within the same call."""
    responses.get(f"{BASE_URL}/2026/export", body=requests.exceptions.ConnectionError("reset"))
    responses.get(f"{BASE_URL}/2026/export", json={"transactions": {}})
    slept = []
    clock = FakeClock()
    client = make_client(sleep=slept.append, clock=clock)
    assert client.transactions(2026) == {"transactions": {}}
    assert slept == [pytest.approx(1.0)]  # paced before the retry too, same as any request


@responses.activate
def test_connection_errors_give_up_after_exhausting_retries():
    responses.get(f"{BASE_URL}/2026/export", body=requests.exceptions.ConnectionError("reset"))
    responses.get(f"{BASE_URL}/2026/export", body=requests.exceptions.ConnectionError("reset"))
    responses.get(f"{BASE_URL}/2026/export", body=requests.exceptions.ConnectionError("reset"))
    client = make_client(sleep=lambda s: None)
    with pytest.raises(MflError, match="reset"):
        client.transactions(2026)
    assert len(responses.calls) == 3


@responses.activate
def test_a_timeout_is_not_retried():
    """This client is shared with the notifier Lambda's tight processing budget (see
    poller.py's RUN_TIME_BUDGET_SECONDS); blindly retrying a slow request that times out,
    rather than just a fast connection reset, could blow it. Only ConnectionError is retried."""
    responses.get(f"{BASE_URL}/2026/export", body=requests.exceptions.Timeout("slow"))
    client = make_client(sleep=lambda s: None)
    with pytest.raises(MflError, match="slow"):
        client.transactions(2026)
    assert len(responses.calls) == 1


@responses.activate
def test_two_clients_sharing_a_pacer_are_paced_against_each_other():
    """Two MflClient instances for different league ids (e.g. one season under a different MFL
    league id than the current one) sharing one requests.Session must also share pacing, or the
    second client fires immediately with no memory of the first client's last request."""
    responses.get(f"{BASE_URL}/2016/export", json={"transactions": {}})
    responses.get(f"{BASE_URL}/2026/export", json={"transactions": {}})
    slept = []
    clock = FakeClock()
    pacer = RequestPacer()
    first = make_client(league_id="79873", sleep=slept.append, clock=clock, pacer=pacer)
    second = make_client(league_id=LEAGUE_ID, sleep=slept.append, clock=clock, pacer=pacer)
    first.transactions(2016)
    clock.now = 100.4
    second.transactions(2026)
    assert slept == [pytest.approx(0.6)]


@responses.activate
def test_no_sleep_when_more_than_a_second_has_passed():
    responses.get(f"{BASE_URL}/2026/export", json={"transactions": {}})
    responses.get(f"{BASE_URL}/2026/export", json={"transactions": {}})
    slept = []
    clock = FakeClock()
    client = make_client(sleep=slept.append, clock=clock)
    client.transactions(2026)
    clock.now += 5.0
    client.transactions(2026)
    assert slept == []


@responses.activate
def test_league_logs_error_body_and_returns_none(caplog):
    import logging

    responses.get(f"{BASE_URL}/2026/export", json={"error": {"$t": "Invalid league ID 1"}})
    with caplog.at_level(logging.WARNING):
        assert make_client().league(2026) is None
    assert "Invalid league ID 1" in caplog.text


@responses.activate
def test_default_timeout_is_split_connect_read():
    session = requests.Session()
    seen = {}
    original = session.get

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return original(*args, **kwargs)

    session.get = spy
    responses.get(f"{BASE_URL}/2026/export", json={"transactions": {}})
    make_client(session=session).transactions(2026)
    assert seen["timeout"] == (3.05, 7.0)


@responses.activate
def test_detect_league_strips_whitespace_from_names():
    body = league_body(2026, [2026], franchises=[{"id": "0007", "name": "Free Hernandez Bad Boyz "}, {"id": "0008", "name": "   "}])
    body["league"]["name"] = "  BDFL  "
    responses.get(f"{BASE_URL}/2026/export", json=body)
    league = make_client().detect_league(NOW)
    assert league.name == "BDFL"
    assert league.franchises == {"0007": "Free Hernandez Bad Boyz", "0008": "Franchise 0008"}


@responses.activate
def test_players_strips_the_id_key_too():
    responses.get(f"{BASE_URL}/2026/export", json={"players": {"player": [
        {"id": " 13299 ", "name": "Kittle, George", "team": "SFO", "position": "TE"},
    ]}})
    players = make_client().players(2026, ["13299"])
    assert list(players) == ["13299"]
    assert players["13299"].id == "13299"


@responses.activate
def test_export_passes_params_and_returns_body():
    responses.get(
        f"{BASE_URL}/2020/export",
        json={"weeklyResults": {"week": "1"}},
        match=[
            responses.matchers.query_param_matcher(
                {"TYPE": "weeklyResults", "L": LEAGUE_ID, "JSON": "1", "W": "1"}
            )
        ],
    )
    assert make_client().export(2020, "weeklyResults", W="1") == {"weeklyResults": {"week": "1"}}


@responses.activate
def test_export_raises_on_error_body():
    responses.get(f"{BASE_URL}/2016/export", json={"error": {"$t": "Invalid league ID 65522"}})
    with pytest.raises(MflError, match="Invalid league ID"):
        make_client().export(2016, "league")
