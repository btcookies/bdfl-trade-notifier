import filecmp
import re
from dataclasses import replace
from pathlib import Path

import pytest
from synthetic import four_team_league

from hof.config import Config, HallRules
from hof.site.build import build_site, current_season, tenure_segments, tint
from hof.site.slugs import slugify, unique_slugs
from hof.stats.careers import Career, Stint
from hof.stats.model import compute

CONFIG = Config(
    league_id="1",
    site_base_url="https://example.test/hof/",
    league_overrides={},
    # a1's 2020 (finished-season) vor is 36.0, the only one of the four to clear 30 (a3's is
    # 22.0; see test_hof_franchises and test_hof_records for the arithmetic).
    hall=HallRules(player_min_vor=30, player_min_starts=3, franchise_min_titles=1, watch_list_margin=50),
    managers=(),
)


def build_synthetic(out: Path):
    model = compute(four_team_league().seasons, CONFIG.hall)
    return build_site(model, CONFIG, out), model


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    site, model = build_synthetic(out)
    return out, site, model


def read(out: Path, relative: str) -> str:
    return (out / relative / "index.html").read_text()


def test_slugify():
    assert slugify("Marcus Peters' Peter Peckers") == "marcus-peters-peter-peckers"
    assert slugify("  Free Hernandez  Bad Boyz ") == "free-hernandez-bad-boyz"
    assert slugify("Ezekiel 23:20") == "ezekiel-23-20"
    assert slugify("Björk & Co.") == "bjork-co"
    assert slugify("!!!") == "franchise"


def test_unique_slugs_disambiguate_collisions():
    assert unique_slugs({"a": "Alpha", "b": "alpha!", "c": "Beta"}) == {"a": "alpha", "b": "alpha-2", "c": "beta"}


def test_site_urls(built):
    _, site, _ = built
    assert site.base_path == "/hof/"
    assert site.url("home") == "/hof/"
    assert site.url("player", "a1") == "/hof/players/qb-a1-a1/"
    assert site.url("franchise", "0001") == "/hof/franchises/alpha-prime/"
    assert site.url("hall") == "/hof/hall-of-fame/"
    assert site.url("draft", 2020) == "/hof/drafts/2020/"
    assert site.url("static", "site.css") == "/hof/static/site.css"


def test_home_page_and_static_assets(built):
    out, _, _ = built
    html = read(out, "")
    assert "<title>Home · BDFL Hall of Records</title>" in html
    assert 'href="/hof/static/site.css"' in html
    assert "Class of 2020" in html and "QB A1" in html
    assert "2020" in html and ">Alpha<" in html and ">Gamma<" in html  # champion and runner-up by their 2020 names
    assert "through 2021 Week 1" in html
    assert (out / "static" / "site.css").exists() and (out / "static" / "site.js").exists()


def assert_same_tree(comparison: filecmp.dircmp) -> None:
    assert not comparison.diff_files and not comparison.left_only and not comparison.right_only, comparison.report()
    for sub in comparison.subdirs.values():
        assert_same_tree(sub)


def test_build_is_deterministic(tmp_path):
    build_synthetic(tmp_path / "one")
    build_synthetic(tmp_path / "two")
    assert_same_tree(filecmp.dircmp(tmp_path / "one", tmp_path / "two"))


def test_build_replaces_a_previous_build(tmp_path):
    out = tmp_path / "site"
    out.mkdir()
    (out / "stale.html").write_text("old")
    build_synthetic(out)
    assert not (out / "stale.html").exists()


def all_html(out: Path) -> dict[str, str]:
    return {str(path.relative_to(out)): path.read_text() for path in out.rglob("*.html")}


def test_no_franchise_id_reaches_the_html(built):
    out, _, _ = built
    leak = re.compile(r"(?<![\d-])000[1-4](?!\d)")
    for name, html in all_html(out).items():
        assert not leak.search(html), f"franchise id in {name}"


def test_players_index_lists_every_career_sorted_by_value(built):
    out, _, _ = built
    html = read(out, "players")
    assert 'id="player-search"' in html
    assert re.findall(r'data-name="([^"]+)"', html) == ["qb a1", "qb a3", "qb a2", "qb a4"]
    assert 'href="/hof/players/qb-a1-a1/"' in html
    assert "Alpha Prime" in html  # franchises are listed by current name


def test_player_page_tells_the_whole_story(built):
    out, _, _ = built
    html = read(out, "players/qb-a1-a1")
    assert "<h1>QB A1" in html
    assert "Hall of Fame · Class of 2020" in html
    assert ">Alpha<" in html and ">Alpha Prime<" in html  # season rows use the name at the time
    assert "Joined Alpha" in html
    assert "🏆" in html
    assert "97.0" in html and "41.0" in html and "Career" in html
    assert 'class="tenure"' in html and "width:100.00%" in html
    assert "Active" in html
    inactive = read(out, "players/qb-a3-a3")
    assert "Active" not in inactive and "Left Gamma" in inactive


def test_tenure_segments_renders_gaps_and_multiple_franchises(built):
    _, site, model = built
    index = {(2020, w): w - 1 for w in range(1, 6)}  # weeks 1..5 -> positions 0..4
    stints = (
        Stint(player_id="zz", franchise_id="0001", start=(2020, 1), end=(2020, 1)),
        # gap: weeks 2-3 off every roster
        Stint(player_id="zz", franchise_id="0002", start=(2020, 4), end=(2020, 5)),
    )
    career = Career(
        player_id="zz", name="Test Player", position="QB",
        first_year=2020, last_year=2020, active=False,
        seasons=(), stints=stints, moves=(),
        starts=0, points=0.0, vor=0.0, bench_points=0.0,
        playoff_starts=0, playoff_points=0, titles=0,
        franchise_ids=("0001", "0002"),
    )
    segments = tenure_segments(career, index, model, site)
    # 3 segments: franchise 0001 (1 week), gap (2 weeks), franchise 0002 (2 weeks) -- total 5 weeks
    assert len(segments) == 3
    assert segments[0]["color"] == site.colors["0001"]
    assert segments[1]["color"] is None  # the gap
    assert segments[2]["color"] == site.colors["0002"]
    widths = [float(s["width"]) for s in segments]
    assert sum(widths) == pytest.approx(100.0)
    assert widths[0] == pytest.approx(20.0)  # 1 of 5 weeks
    assert widths[1] == pytest.approx(40.0)  # 2 of 5 weeks (the gap)
    assert widths[2] == pytest.approx(40.0)  # 2 of 5 weeks
    assert model.league.current_name("0002") in segments[2]["label"]


def test_franchises_index_ranks_by_win_percentage(built):
    out, _, _ = built
    html = read(out, "franchises")
    names = re.findall(r'<td class="l[^"]*"><a href="/hof/franchises/[^"]+/">([^<]+)</a>', html)  # table cells only, not the grid link
    assert names == ["Gamma", "Alpha Prime", "Delta", "Beta"]
    assert "1.000" in html and ".667" in html


def test_franchise_page_groups_seasons_by_era(built):
    out, _, _ = built
    html = read(out, "franchises/alpha-prime")
    assert "<h1>Alpha Prime" in html
    assert "Formerly" in html and "<b>Alpha</b> (2020)" in html
    assert "As Alpha Prime" in html and "As Alpha <small>" in html
    assert html.index("As Alpha Prime") < html.index("As Alpha <small>")  # newest era first
    assert "Champion" in html and "In progress" in html
    assert "<b>2-1-0</b>" in html  # all-time record in the summary row
    assert "Head-to-head" in html and "<summary>" in html and ">Beta<" in html and "2-0-0" in html
    assert "Final" in html and "Semifinal" in html  # playoff history
    assert 'href="/hof/players/qb-a1-a1/">QB A1</a>' in html
    assert "No draft picks" in html and "No trades" in html


def test_records_page_has_every_table(built):
    out, _, model = built
    html = read(out, "records")
    for table in model.records:
        assert table.title in html
    assert "Team, single game" in html and "Player, career" in html
    assert 'href="/hof/players/qb-a1-a1/">QB A1</a>' in html
    assert 'href="/hof/franchises/alpha-prime/">Alpha</a>' in html  # the name at the time links to the current page
    assert "vs Gamma, 2020 Week 4 (Final)" in html
    assert "1.000" in html  # best record, formatted as a percentage
    assert "Luckiest season" in html and "+0.7" in html  # the wins unit renders signed


def test_hall_of_fame_page(built):
    out, _, _ = built
    html = read(out, "hall-of-fame")
    assert "Class of 2020" in html
    assert 'href="/hof/players/qb-a1-a1/"' in html and "Alpha Prime" in html
    # a2's full career vor is -2.0 (2020's -2.0 plus 2021 Week 1's 0.0); needed = 30 - (-2) = 32.0.
    assert "Watch list" in html and "QB A2" in html and "32.0" in html
    assert "30.0 value over replacement" in html and "3 starts" in html and "1 title" in html


def test_drafts_and_trades_pages_exist_with_empty_states(built):
    out, _, _ = built
    assert "No drafts recorded" in read(out, "drafts")
    assert "No trades recorded" in read(out, "trades")


def test_draft_callout_separates_steal_and_bust_with_a_space(built):
    from hof.site.build import environment
    from hof.stats.drafts import DraftSummary, PickLine

    _, site, model = built

    def pick(round_, pick_no, name):
        return PickLine(
            year=2020, round=round_, pick=pick_no, franchise_id="0001", franchise_name="Alpha Prime",
            original_owner_id=None, player_id="zz", player_name=name, position="QB",
            starts_for=1, points_for=10.0, vor_for=5.0, career_points=10.0, career_vor=5.0,
        )
    steal = pick(3, 1, "Steal Guy")
    bust = pick(1, 1, "Bust Guy")
    summary = DraftSummary(year=2020, startup=False, rounds=3, picks=(steal, bust), steal=steal, bust=bust)

    env = environment(model, CONFIG, site)
    html = env.get_template("draft.html").render(d=summary)
    assert "Steal Guy" in html and "Bust Guy" in html
    assert "VOR.<b>Bust:</b>" not in html  # the bug: fragments ran together with no separator
    assert "VOR. <b>Bust:</b>" in html


CONFIG_PATH = Path(__file__).resolve().parents[2] / "data" / "config.toml"


def test_internal_links_resolve(built):
    out, site, _ = built
    for name, html in all_html(out).items():
        for href in re.findall(r'href="([^"]+)"', html):
            if not href.startswith(site.base_path):
                continue
            path = href[len(site.base_path):].split("#")[0]
            target = (out / path / "index.html") if (path == "" or path.endswith("/")) else out / path
            assert target.exists(), f"{name} links to {href}"


def test_real_2020_fixture_builds_a_full_site(tmp_path, fixtures_dir):
    from hof.snapshots import load_season

    config = Config.load(CONFIG_PATH)
    model = compute([load_season(fixtures_dir / "raw" / "2020")], config.hall)
    out = tmp_path / "dist"
    site = build_site(model, config, out)
    assert site.base_path == "/bdfl-trade-notifier/"
    pages = all_html(out)
    assert sum(1 for name in pages if name.startswith("franchises/") and name not in ("franchises/index.html", "franchises/rivalries/index.html")) == 12
    assert "franchises/rivalries/index.html" in pages and "seasons/2020/index.html" in pages
    assert sum(1 for name in pages if name.startswith("players/") and name != "players/index.html") > 100
    assert len(re.findall(r'data-sort="\d+"', pages["drafts/2020/index.html"])) == 48
    assert pages["trades/index.html"].count('class="trade"') == 20
    home = pages["index.html"]
    assert "Marcus Peters&#39; Peter Peckers" in home  # autoescaped apostrophe
    assert "through 2020 Week 16" in home
    leak = re.compile(r"(?<![\d-])00(0[1-9]|1[0-2])(?!\d)")
    for name, html in pages.items():
        assert not leak.search(html), f"franchise id in {name}"


def test_cli_build_writes_the_site(tmp_path, fixtures_dir, capsys):
    from hof import __main__ as cli

    out = tmp_path / "dist"
    code = cli.main(["--data", str(fixtures_dir), "--config", str(CONFIG_PATH), "build", "--out", str(out)])
    assert code == 0
    assert (out / "index.html").exists()
    assert "built" in capsys.readouterr().out


def test_new_site_urls_and_nav(built):
    out, site, _ = built
    assert site.url("seasons") == "/hof/seasons/"
    assert site.url("season", 2020) == "/hof/seasons/2020/"
    assert site.url("rivalries") == "/hof/franchises/rivalries/"
    assert 'href="/hof/seasons/">Seasons</a>' in read(out, "")


def test_tint_runs_from_red_through_grey_to_green():
    assert tint((0, 0, 0)) == "#f4f4f4" and tint((1, 1, 0)) == "#f4f4f4" and tint((0, 0, 2)) == "#f4f4f4"
    assert tint((2, 0, 0)) == "#a3d9b0" and tint((0, 2, 0)) == "#e8a8a8"
    assert tint((3, 1, 0)) == "#cce7d2"  # halfway to green


def test_seasons_index_lists_newest_first(built):
    out, _, _ = built
    html = read(out, "seasons")
    assert 'href="/hof/seasons/2021/">2021</a>' in html and 'href="/hof/seasons/2020/">2020</a>' in html
    assert html.index('href="/hof/seasons/2021/"') < html.index('href="/hof/seasons/2020/"')
    assert ">Alpha<" in html and ">Gamma<" in html  # 2020 champion and runner-up by their 2020 names
    assert "2-0-0" in html and "33.0" in html  # best record and most points (Gamma)
    assert ">Delta</a> +0.7" in html  # luckiest
    assert ">Alpha</a> (15)" in html  # awards leader
    assert "through Week 1" in html  # 2021 has no champion yet


def test_season_page_for_a_finished_season(built):
    out, _, _ = built
    html = read(out, "seasons/2020")
    assert "<h1>2020 season" in html and "Final" in html
    assert "Alpha won the title, 30.0–20.0 over Gamma." in html
    names = re.findall(r'<td class="l key"><a href="/hof/franchises/[^"]+/">([^<]+)</a></td>', html)
    assert names[:4] == ["Gamma", "Alpha", "Delta", "Beta"]  # standings come first, in standings order
    assert "5-1-0" in html and "1.67" in html and "-0.7" in html and "+0.7" in html
    assert "Power rankings" in html and "through Week 2" in html
    assert "▲1" in html and "▼1" in html and "0.883" in html and "Score = 0.5 × all-play %" in html
    assert "<h3>Week 4" in html and "<h3>Week 1" in html and html.index("<h3>Week 4") < html.index("<h3>Week 1")
    assert "Highest score" in html and "would have gone 2-1-0 against the field" in html
    assert "Awards tally" in html and "<td>15</td>" in html


def test_season_page_for_the_season_in_progress(built):
    out, _, _ = built
    html = read(out, "seasons/2021")
    assert "through Week 1" in html and "won the title" not in html
    assert ">new<" in html  # first ranked week
    assert ">Alpha Prime</a>" in html


def test_rivalries_page(built):
    out, _, _ = built
    html = read(out, "franchises/rivalries")
    rows = re.findall(r'<td class="l key"><a href="/hof/franchises/([^"]+)/">', html)
    assert rows == ["gamma", "alpha-prime", "delta", "beta"]
    assert "<th>1</th><th>2</th><th>3</th><th>4</th>" in html
    assert 'href="/hof/franchises/alpha-prime/#h2h">2-0</a>' in html
    assert 'href="/hof/franchises/beta/#h2h">0-2</a>' in html
    assert 'class="self"' in html and "#a3d9b0" in html and "#e8a8a8" in html
    assert "Most played" in html and "Most lopsided" in html and "Most even" in html
    assert "Alpha Prime</a> 2-0 <a" in html and "2 meetings" in html
    assert "Nobody has met 5 times yet." in html
    assert 'href="/hof/franchises/rivalries/"' in read(out, "franchises")


def test_franchise_page_has_all_play_luck_awards_and_rivalry_link(built):
    out, _, _ = built
    html = read(out, "franchises/alpha-prime")
    assert "<b>.857</b><span>All-play</span>" in html
    assert "<b>-0.7</b><span>Luck</span>" in html
    assert "Weekly awards: 21" in html and "Highest score 4" in html and 'href="/hof/seasons/"' in html
    assert '<h2 id="h2h">' in html and 'href="/hof/franchises/rivalries/"' in html
    assert "<th>Luck</th>" in html and '<th class="p2">All-play</th>' in html
    assert 'href="/hof/seasons/2020/">2020</a>' in html
    assert "<td class=\"p2\">5-1-0</td>" in html and "<td>-0.7</td>" in html
    assert 'data-label="Reg">' in html
    for details in re.findall(r"<details>.*?</details>", html, re.S):
        assert '<div class="table-wrap">' in details
    beta = read(out, "franchises/beta")
    assert "Weekly awards: 6" in beta  # 4 in 2020, 2 in 2021


def test_home_links_seasons_and_shows_the_season_in_progress(built):
    out, _, _ = built
    html = read(out, "")
    assert 'href="/hof/seasons/2020/">2020</a>' in html
    assert "<b>2021</b> · through Week 1 ·" in html and 'href="/hof/seasons/2021/"' in html
    assert '<td class="l key"><a href="/hof/franchises/alpha-prime/">Alpha</a></td>' in html


def test_current_season_ends_when_the_final_is_decided():
    league = four_team_league()
    assert current_season(compute(league.seasons, CONFIG.hall)).year == 2021  # one game played, no final
    decided = replace(league.season(2020), complete=False)  # final played, February not yet reached
    assert current_season(compute([decided], CONFIG.hall)) is None


def test_priority_and_key_classes_are_on_every_wide_table(built):
    out, _, _ = built
    assert '<th class="l key">Player</th><th>Pos</th><th class="p3">Years</th>' in read(out, "players")
    assert '<th class="rank">#</th><th class="l key">Holder</th><th>Mark</th><th class="l p2">Detail</th>' in read(out, "records")
    assert '<th class="key">Year</th><th class="l">Franchise</th><th>GS</th><th>Pts</th><th>VOR</th><th class="p2">Bench</th>' in read(out, "players/qb-a1-a1")
    assert '<th class="l key">Franchise</th><th>Record</th><th class="p2">Pct</th>' in read(out, "franchises")
    assert '<th class="l key">Player</th><th>Pos</th><th class="p3">GS</th>' in read(out, "hall-of-fame")
    css = (out / "static" / "site.css").read_text()
    assert "@media (max-width: 720px) { .p3 { display: none; } }" in css
    assert "@media (max-width: 480px) { .p2 { display: none; } }" in css
    assert "position: sticky" in css and "background-attachment: local" in css
    assert 'span[data-label]::before { content: attr(data-label) " "; }' in css
