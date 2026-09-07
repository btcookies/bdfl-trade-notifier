"""Discord embed for the season wrap.

Minimal placeholder: only the title (and a link back to the site) that Task 1's tests pin down.
The full embed body -- top scorer, best VOR, best manager, most left on the bench, and the
champion -- is built out in Task 3.
"""

from __future__ import annotations

from typing import Any

from hof.stats.milestones import SeasonAwards
from hof.stats.model import Model


def wrap_embed(model: Model, year: int, awards: SeasonAwards, site_url: str) -> dict[str, Any]:
    return {
        "title": f"🏆 {year} season wrap",
        "url": site_url,
    }
