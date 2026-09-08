import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from synthetic import four_team_league

from hof.config import HallRules
from hof.discord import notify
from hof.discord.notify import Decision, State
from hof.stats.league import League
from hof.stats.model import compute

RULES = HallRules(player_min_vor=30, player_min_starts=3, franchise_min_titles=1)
LOCKS = (1_000, 2_000, 3_000, 4_000)  # 2020 weeks 1 to 4
HOURS = 3600


def league_with_locks(week4_scored: bool = True) -> League:
    """The synthetic league with lock times on 2020 and, optionally, week 4 left unscored."""
    league = four_team_league()
    s2020 = league.season(2020)
    s2020 = replace(s2020, transactions=replace(s2020.transactions, lock_times=LOCKS))
    if not week4_scored:
        week4 = s2020.weeks[4]
        lineups = {fid: replace(lineup, score=None) for fid, lineup in week4.lineups.items()}
        s2020 = replace(s2020, weeks={**s2020.weeks, 4: replace(week4, lineups=lineups)})
    s2021 = league.season(2021)
    s2021 = replace(s2021, transactions=replace(s2021.transactions, lock_times=(10_000,)))
    return League.build([s2020, s2021])


def at(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch, UTC)


def test_week_is_complete_forty_hours_after_its_lock():
    season = league_with_locks().season(2020)
    assert notify.week_complete(season, 3, at(3_000 + 40 * HOURS - 1)) is False
    assert notify.week_complete(season, 3, at(3_000 + 40 * HOURS)) is True
    assert notify.week_complete(season, 5, at(10 ** 9)) is False  # no such lock


def test_week_with_an_unscored_matchup_is_not_complete():
    season = league_with_locks(week4_scored=False).season(2020)
    assert notify.week_complete(season, 4, at(10 ** 9)) is False
    assert notify.week_complete(season, 3, at(10 ** 9)) is True


def test_newest_complete_week_prefers_the_newest_season():
    league = league_with_locks()
    assert notify.newest_complete_week(league, at(10_000 + 40 * HOURS)) == (2021, 1)
    assert notify.newest_complete_week(league, at(4_000 + 40 * HOURS)) == (2020, 4)
    assert notify.newest_complete_week(league, at(500)) is None


def test_state_round_trip(tmp_path):
    path = tmp_path / "notify-state.json"
    assert notify.load_state(path) is None
    notify.save_state(path, State(2020, 4, "wrap"))
    assert json.loads(path.read_text()) == {"season": 2020, "week": 4, "kind": "wrap"}
    assert notify.load_state(path) == State(2020, 4, "wrap")


def test_decide_recap_wrap_and_nothing():
    league = league_with_locks()
    model = compute(league.seasons, RULES)
    # 2020 week 4 is the final: a wrap
    assert notify.decide(model, None, at(4_000 + 40 * HOURS)) == Decision("wrap", 2020, 4)
    # a regular-season week: a recap
    assert notify.decide(model, None, at(3_000 + 40 * HOURS)) == Decision("recap", 2020, 3)
    # already posted
    assert notify.decide(model, State(2020, 3, "recap"), at(3_000 + 40 * HOURS)) is None
    # posted an older week: post the newest complete one only
    assert notify.decide(model, State(2020, 1, "recap"), at(4_000 + 40 * HOURS)) == Decision("wrap", 2020, 4)
    # nothing complete yet
    assert notify.decide(model, None, at(500)) is None


@pytest.mark.parametrize(
    "url, ok",
    [
        ("https://discord.com/api/webhooks/123/abc", True),
        ("https://discordapp.com/api/webhooks/123/abc", True),
        ("http://discord.com/api/webhooks/123/abc", False),
        ("https://example.com/api/webhooks/123/abc", False),
        ("https://discord.com/api/other/123", False),
        ("", False),
    ],
)
def test_webhook_url_check(url, ok):
    if ok:
        assert notify.webhook_url({"DISCORD_WEBHOOK_URL": url}) == url
    else:
        with pytest.raises(notify.NotifyError):
            notify.webhook_url({"DISCORD_WEBHOOK_URL": url})


def test_run_posts_once_and_records_state(tmp_path):
    league = league_with_locks()
    model = compute(league.seasons, RULES)
    posted: list[list[dict]] = []

    class FakeWebhook:
        def post(self, embeds):
            posted.append(embeds)

    path = tmp_path / "notify-state.json"
    now = at(3_000 + 40 * HOURS)
    outcome = notify.run(model, "https://example.test/", path, now, FakeWebhook())
    assert outcome.posted and outcome.decision == Decision("recap", 2020, 3)
    assert len(posted) == 1 and posted[0][0]["title"] == "📜 Week 3 in the record books"
    assert notify.load_state(path) == State(2020, 3, "recap")

    again = notify.run(model, "https://example.test/", path, now, FakeWebhook())
    assert not again.posted and "already posted" in again.reason
    assert len(posted) == 1


def test_run_leaves_state_alone_when_the_post_fails(tmp_path):
    league = league_with_locks()
    model = compute(league.seasons, RULES)

    class FailingWebhook:
        def post(self, embeds):
            raise RuntimeError("boom")

    path = tmp_path / "notify-state.json"
    with pytest.raises(RuntimeError):
        notify.run(model, "https://example.test/", path, at(3_000 + 40 * HOURS), FailingWebhook())
    assert notify.load_state(path) is None


def test_run_dry_run_prints_without_posting_or_saving(tmp_path, capsys):
    league = league_with_locks()
    model = compute(league.seasons, RULES)
    path = tmp_path / "notify-state.json"
    outcome = notify.run(model, "https://example.test/", path, at(4_000 + 40 * HOURS), webhook=None, dry_run=True)
    assert not outcome.posted and outcome.decision == Decision("wrap", 2020, 4)
    out = capsys.readouterr().out
    assert json.loads(out)["title"] == "🏆 2020 season wrap"
    assert notify.load_state(path) is None


def test_run_forced_week_ignores_state(tmp_path, capsys):
    league = league_with_locks()
    model = compute(league.seasons, RULES)
    path = tmp_path / "notify-state.json"
    notify.save_state(path, State(2021, 1, "recap"))
    outcome = notify.run(model, "https://example.test/", path, at(10 ** 9), webhook=None, dry_run=True, force=(2020, 2))
    assert outcome.decision == Decision("recap", 2020, 2)
    assert json.loads(capsys.readouterr().out)["title"] == "📜 Week 2 in the record books"


def test_run_forced_post_never_writes_state(tmp_path):
    league = league_with_locks()
    model = compute(league.seasons, RULES)
    posted: list[list[dict]] = []

    class FakeWebhook:
        def post(self, embeds):
            posted.append(embeds)

    path = tmp_path / "notify-state.json"
    notify.save_state(path, State(2021, 1, "recap"))
    outcome = notify.run(model, "https://example.test/", path, at(10 ** 9), FakeWebhook(), force=(2020, 2))
    assert outcome.posted and outcome.decision == Decision("recap", 2020, 2)
    assert len(posted) == 1 and posted[0][0]["title"] == "📜 Week 2 in the record books"
    # a forced post must never touch the state file, even on a real (non-dry-run) post
    assert notify.load_state(path) == State(2021, 1, "recap")
