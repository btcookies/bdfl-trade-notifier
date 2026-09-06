import json
import re
import urllib.parse
from datetime import UTC, date, datetime

import pytest
import responses

from bdfl.mfl import BASE_URL, MflClient, MflError
from hof import fetch
from hof.config import Config, HallRules

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
CONFIG = Config(
    league_id="65522",
    site_base_url="https://example.test/",
    league_overrides={2016: "79873"},
    hall=HallRules(),
    managers=(),
)


def league_body(league_id, years, end_week=2):
    return {
        "league": {
            "id": league_id,
            "name": "BDFL",
            "startWeek": "1",
            "endWeek": str(end_week),
            "history": {"league": [{"year": str(y), "url": f"https://x/{y}"} for y in years]},
            "franchises": {"franchise": [{"id": "0001", "name": "A"}, {"id": "0002", "name": "B"}]},
        }
    }


def week_body(week):
    return {
        "weeklyResults": {
            "week": str(week),
            "matchup": [
                {
                    "franchise": [
                        {
                            "id": "0001",
                            "score": "10.0",
                            "starters": "101,102,",
                            "nonstarters": "103,",
                            "player": [{"id": "101", "score": "5.0", "status": "starter"}],
                        },
                        {
                            "id": "0002",
                            "score": "8.0",
                            "starters": "104,",
                            "nonstarters": "",
                            "player": [{"id": "104", "score": "8.0", "status": "starter"}],
                        },
                    ]
                }
            ],
        }
    }


def players_body(query):
    ids = query["PLAYERS"].split(",")
    return {
        "players": {
            "player": [
                {"id": i, "name": f"Last{i}, First", "position": "RB", "team": "SF"} for i in ids
            ]
        }
    }


def season_handlers(year, league_id, years, weeks=2):
    return {
        (year, "league"): league_body(league_id, years, end_week=weeks),
        (year, "standings"): {"leagueStandings": {"franchise": []}},
        (year, "schedule"): {"schedule": {"weeklySchedule": []}},
        (year, "playoffBrackets"): {"playoffBrackets": {}},
        (year, "playoffBracket"): {"playoffBracket": {"bracket_id": "1", "playoffRound": []}},
        (year, "draftResults"): {
            "draftResults": {
                "draftUnit": {
                    "draftPick": [
                        {"round": "01", "pick": "01", "franchise": "0001", "player": "201", "timestamp": "1"}
                    ]
                }
            }
        },
        (year, "transactions"): {
            "transactions": {
                "transaction": [
                    {
                        "type": "TRADE",
                        "timestamp": "5",
                        "franchise": "0001",
                        "franchise2": "0002",
                        "franchise1_gave_up": "301,",
                        "franchise2_gave_up": "BB_5,",
                    }
                ]
            }
        },
        (year, "weeklyResults"): lambda q: week_body(int(q["W"])),
        (year, "players"): players_body,
    }


def stub_mfl(handlers):
    """Route every MFL GET to handlers[(year, TYPE)]: a body, or a callable taking the query."""

    def callback(request):
        parsed = urllib.parse.urlparse(request.url)
        query = dict(urllib.parse.parse_qsl(parsed.query))
        year = int(parsed.path.split("/")[1])
        handler = handlers.get((year, query["TYPE"]))
        if handler is None:
            body = {"error": {"$t": f"no stub for {year} {query['TYPE']}"}}
        else:
            body = handler(query) if callable(handler) else handler
        return 200, {"Content-Type": "application/json"}, json.dumps(body)

    responses.add_callback(
        responses.GET, re.compile(rf"{re.escape(BASE_URL)}/\d{{4}}/export.*"), callback=callback
    )


def requested(year=None, type_=None):
    """Query dicts of every MFL call made so far, optionally filtered."""
    out = []
    for call in responses.calls:
        parsed = urllib.parse.urlparse(call.request.url)
        query = dict(urllib.parse.parse_qsl(parsed.query))
        called_year = int(parsed.path.split("/")[1])
        if (year is None or called_year == year) and (type_ is None or query["TYPE"] == type_):
            out.append(query)
    return out


def make_factory():
    def factory(league_id):
        return MflClient(league_id=league_id, user_agent="test", sleep=lambda s: None)

    return factory


SEASON_FILES = [
    "league.json",
    "standings.json",
    "schedule.json",
    "playoffBrackets.json",
    "playoffBracket-1.json",
    "draftResults.json",
    "transactions.json",
    "players.json",
    "meta.json",
    "weeklyResults/W01.json",
    "weeklyResults/W02.json",
]


@responses.activate
def test_run_fetches_every_season_in_history_with_league_id_overrides(tmp_path):
    stub_mfl({**season_handlers(2026, "65522", [2016, 2026]), **season_handlers(2016, "79873", [2016, 2026])})

    fetched = fetch.run(tmp_path, CONFIG, NOW, make_factory())

    assert fetched == [2016, 2026]
    assert {q["L"] for q in requested(2016)} == {"79873"}
    assert {q["L"] for q in requested(2026)} == {"65522"}
    for year in (2016, 2026):
        for name in SEASON_FILES:
            assert (tmp_path / "raw" / str(year) / name).exists(), f"{year}/{name}"
    assert json.loads((tmp_path / "raw" / "2016" / "meta.json").read_text())["complete"] is True
    meta_2026 = json.loads((tmp_path / "raw" / "2026" / "meta.json").read_text())
    assert meta_2026["complete"] is False
    assert meta_2026["league_id"] == "65522"
    players = json.loads((tmp_path / "raw" / "2026" / "players.json").read_text())
    assert {p["id"] for p in players["players"]["player"]} == {"101", "102", "103", "104", "201", "301"}
    assert not list((tmp_path / "raw").glob(".*.tmp"))


@responses.activate
def test_run_skips_seasons_marked_complete(tmp_path):
    done = tmp_path / "raw" / "2016"
    done.mkdir(parents=True)
    (done / "meta.json").write_text(json.dumps({"complete": True}))
    stub_mfl(season_handlers(2026, "65522", [2016, 2026]))

    assert fetch.run(tmp_path, CONFIG, NOW, make_factory()) == [2026]
    assert requested(2016) == []


@responses.activate
def test_run_refetches_a_season_marked_complete_under_a_stale_league_id(tmp_path):
    """A corrected seasons.overrides entry must invalidate a season fetched under the old id."""
    done = tmp_path / "raw" / "2016"
    done.mkdir(parents=True)
    (done / "meta.json").write_text(json.dumps({"complete": True, "league_id": "65522"}))
    stub_mfl({**season_handlers(2026, "65522", [2016, 2026]), **season_handlers(2016, "79873", [2016, 2026])})

    fetched = fetch.run(tmp_path, CONFIG, NOW, make_factory())

    assert fetched == [2016, 2026]
    assert {q["L"] for q in requested(2016)} == {"79873"}
    meta_2016 = json.loads((tmp_path / "raw" / "2016" / "meta.json").read_text())
    assert meta_2016["league_id"] == "79873"


@responses.activate
def test_run_honors_an_explicit_year_list(tmp_path):
    stub_mfl(season_handlers(2020, "65522", [2020]))

    assert fetch.run(tmp_path, CONFIG, NOW, make_factory(), years=[2020]) == [2020]
    assert requested(2026) == []


@responses.activate
def test_run_resumes_after_a_mid_run_failure(tmp_path):
    """Seasons already written complete before a failure are skipped on a rerun; only the
    interrupted season (and anything after it) is repeated."""
    years = [2020, 2021, 2022, 2023]
    handlers: dict = {}
    for year in years:
        handlers.update(season_handlers(year, "65522", [year]))
    state = {"fail": True}
    handlers[(2022, "weeklyResults")] = lambda q: (
        {"error": {"$t": "throttled"}} if state["fail"] and q["W"] == "2" else week_body(int(q["W"]))
    )
    stub_mfl(handlers)

    with pytest.raises(MflError, match="throttled"):
        fetch.run(tmp_path, CONFIG, NOW, make_factory(), years=years)

    for year in (2020, 2021):
        assert json.loads((tmp_path / "raw" / str(year) / "meta.json").read_text())["complete"] is True
    assert not (tmp_path / "raw" / "2022").exists()
    assert not (tmp_path / "raw" / "2023").exists()
    assert not list((tmp_path / "raw").glob(".*.tmp"))
    calls_after_failure = len(responses.calls)

    state["fail"] = False
    fetched = fetch.run(tmp_path, CONFIG, NOW, make_factory(), years=years)

    assert fetched == [2022, 2023]
    # The already-complete 2020/2021 seasons made no further requests on the rerun; every new
    # call belongs to the two years that still needed (re)fetching.
    new_calls = responses.calls[calls_after_failure:]
    new_years = {int(urllib.parse.urlparse(c.request.url).path.split("/")[1]) for c in new_calls}
    assert new_years == {2022, 2023}


@responses.activate
def test_fetch_season_replaces_nothing_when_a_request_fails(tmp_path):
    season_dir = tmp_path / "raw" / "2026"
    season_dir.mkdir(parents=True)
    (season_dir / "marker").write_text("old")
    handlers = season_handlers(2026, "65522", [2026])
    handlers[(2026, "weeklyResults")] = lambda q: (
        {"error": {"$t": "boom"}} if q["W"] == "2" else week_body(1)
    )
    stub_mfl(handlers)

    with pytest.raises(MflError, match="boom"):
        fetch.fetch_season(make_factory()("65522"), 2026, season_dir, NOW)

    assert (season_dir / "marker").read_text() == "old"
    assert not (season_dir / "league.json").exists()
    assert not list((tmp_path / "raw").glob(".*.tmp"))


@responses.activate
def test_players_are_requested_in_chunks_of_200():
    stub_mfl({(2026, "players"): players_body})
    ids = {str(i) for i in range(450)}

    body = fetch.fetch_players(make_factory()("65522"), 2026, ids)

    sizes = [len(q["PLAYERS"].split(",")) for q in requested(2026, "players")]
    assert sizes == [200, 200, 50]
    assert {p["id"] for p in body["players"]["player"]} == ids


def test_referenced_player_ids_covers_lineups_draft_and_transactions():
    weekly = [week_body(1)]
    draft = {"draftResults": {"draftUnit": {"draftPick": [{"player": "201"}]}}}
    transactions = {
        "transactions": {
            "transaction": [
                {"type": "TRADE", "franchise1_gave_up": "301,BB_5,", "franchise2_gave_up": "FP_0001_2027_1,"},
                {"type": "BBID_WAIVER", "transaction": "401,|3.00|402,"},
                {"type": "FREE_AGENT", "transaction": "|403,"},
                {"type": "IR", "activated": "404,", "deactivated": ""},
                {"type": "TAXI", "promoted": "", "demoted": "405,"},
            ]
        }
    }
    assert fetch.referenced_player_ids(weekly, draft, transactions) == {
        "101", "102", "103", "104", "201", "301", "401", "402", "403", "404", "405"
    }


def test_season_complete_on_february_first_of_the_next_year():
    assert fetch.season_complete(2025, date(2026, 1, 31)) is False
    assert fetch.season_complete(2025, date(2026, 2, 1)) is True


@responses.activate
def test_discover_seasons_falls_back_to_the_prior_year():
    responses.get(f"{BASE_URL}/2026/export", status=404)
    stub_mfl({(2025, "league"): league_body("65522", [2024, 2025])})

    assert fetch.discover_seasons(make_factory()("65522"), NOW) == [2024, 2025]
