"""Discord embed for the weekly recap.

Minimal placeholder: only the title (and a link back to the site) that Task 1's tests pin down.
The full embed body -- high score, top starter, new records, milestones, series firsts, and the
playoff picture or bracket -- is built out in Task 2.
"""

from __future__ import annotations

from typing import Any

from hof.stats.milestones import RecapFacts


def recap_embed(facts: RecapFacts, site_url: str) -> dict[str, Any]:
    return {
        "title": f"📜 Week {facts.week} in the record books",
        "url": site_url,
    }
