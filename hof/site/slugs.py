"""URL slugs: lowercase ASCII words joined by hyphens."""

from __future__ import annotations

import re
import unicodedata

_NON_WORD = re.compile(r"[^a-z0-9]+")


def slugify(text: str, fallback: str = "franchise") -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = _NON_WORD.sub("-", ascii_text.lower()).strip("-")
    return slug or fallback


def unique_slugs(names: dict[str, str]) -> dict[str, str]:
    """Key -> slug, appending -2, -3, ... when two names slug the same; keys are processed in order."""
    taken: dict[str, int] = {}
    out: dict[str, str] = {}
    for key, name in names.items():
        base = slugify(name)
        count = taken.get(base, 0) + 1
        taken[base] = count
        out[key] = base if count == 1 else f"{base}-{count}"
    return out
