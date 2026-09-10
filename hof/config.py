"""Configuration for the hall of records, read from data/config.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hof.stats.awards import AWARD_KEYS


class ConfigError(ValueError):
    """The config file is missing, malformed, or has an invalid value."""


@dataclass(frozen=True)
class HallRules:
    player_min_vor: float = 400.0
    player_min_starts: int = 30
    franchise_min_titles: int = 2
    watch_list_margin: float = 100.0


@dataclass(frozen=True)
class Manager:
    franchise: str
    name: str
    from_year: int


@dataclass(frozen=True)
class Config:
    league_id: str
    site_base_url: str
    league_overrides: dict[int, str]
    hall: HallRules
    managers: tuple[Manager, ...]
    award_labels: dict[str, str] = field(default_factory=dict)  # award key -> display label

    def league_id_for(self, year: int) -> str:
        return self.league_overrides.get(year, self.league_id)

    @classmethod
    def load(cls, path: Path) -> Config:
        try:
            raw = tomllib.loads(path.read_text())
        except FileNotFoundError:
            raise ConfigError(f"missing config file {path}") from None
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Config:
        league = raw.get("league") or {}
        league_id = str(league.get("id") or "").strip()
        if not league_id.isdigit():
            raise ConfigError("league.id must be the numeric MFL league id")
        base_url = str(league.get("site_base_url") or "").strip()
        if not base_url.startswith("https://"):
            raise ConfigError("league.site_base_url must be an https URL")
        if not base_url.endswith("/"):
            base_url += "/"

        overrides: dict[int, str] = {}
        for year, league in ((raw.get("seasons") or {}).get("overrides") or {}).items():
            if not str(year).isdigit() or not str(league).isdigit():
                raise ConfigError(f"seasons.overrides: bad entry {year!r} = {league!r}")
            overrides[int(year)] = str(league)

        hall_raw = raw.get("hall_of_fame") or {}
        try:
            hall = HallRules(
                player_min_vor=float(hall_raw.get("player_min_vor", HallRules.player_min_vor)),
                player_min_starts=int(hall_raw.get("player_min_starts", HallRules.player_min_starts)),
                franchise_min_titles=int(
                    hall_raw.get("franchise_min_titles", HallRules.franchise_min_titles)
                ),
                watch_list_margin=float(
                    hall_raw.get("watch_list_margin", HallRules.watch_list_margin)
                ),
            )
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"hall_of_fame: {exc}") from exc

        managers = []
        for entry in raw.get("managers") or []:
            try:
                managers.append(
                    Manager(
                        franchise=str(entry["franchise"]),
                        name=str(entry["name"]).strip(),
                        from_year=int(entry.get("from", 0)),
                    )
                )
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                raise ConfigError(f"managers: bad entry {entry!r}") from exc

        labels: dict[str, str] = {}
        for key, label in (raw.get("awards") or {}).items():
            if key not in AWARD_KEYS:
                raise ConfigError(f"awards: unknown award {key!r}; known keys: {', '.join(AWARD_KEYS)}")
            text = str(label).strip()
            if not text:
                raise ConfigError(f"awards: empty label for {key!r}")
            labels[str(key)] = text

        return cls(league_id, base_url, overrides, hall, tuple(managers), labels)
