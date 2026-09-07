import filecmp
import re
from pathlib import Path

import pytest
from synthetic import four_team_league

from hof.config import Config, HallRules
from hof.site.build import build_site
from hof.site.slugs import slugify, unique_slugs
from hof.stats.model import compute

CONFIG = Config(
    league_id="1",
    site_base_url="https://example.test/hof/",
    league_overrides={},
    hall=HallRules(player_min_vor=40, player_min_starts=3, franchise_min_titles=1, watch_list_margin=50),
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
