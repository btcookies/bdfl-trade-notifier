"""Minimal Discord webhook client."""

from __future__ import annotations

import time
from collections.abc import Callable

import requests

MAX_RETRY_AFTER_SECONDS = 5.0


class DiscordError(Exception):
    pass


class DiscordWebhook:
    def __init__(
        self,
        url: str,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        username: str = "BDFL",
        timeout: float = 10.0,
    ):
        self.url = url
        self.session = session or requests.Session()
        self.sleep = sleep
        self.username = username
        self.timeout = timeout

    def post(self, embeds: list[dict]) -> None:
        body = {"username": self.username, "embeds": embeds, "allowed_mentions": {"parse": []}}
        response = self._send(body)
        if response.status_code == 429:
            self.sleep(self._retry_after(response))
            response = self._send(body)
        if not 200 <= response.status_code < 300:
            raise DiscordError(f"Discord webhook returned {response.status_code}: {response.text[:200]}")

    def _send(self, body: dict) -> requests.Response:
        try:
            return self.session.post(
                self.url, params={"wait": "true"}, json=body, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise DiscordError(f"Discord request failed: {exc}") from exc

    @staticmethod
    def _retry_after(response: requests.Response) -> float:
        raw = response.headers.get("Retry-After", "1")
        try:
            seconds = float(raw)
        except ValueError:
            seconds = 1.0
        return min(max(seconds, 0.0), MAX_RETRY_AFTER_SECONDS)
