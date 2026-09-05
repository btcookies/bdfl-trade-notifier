"""Minimal Discord webhook client."""

from __future__ import annotations

import time
from collections.abc import Callable

import requests

from bdfl.messages import MAX_EMBEDS_PER_MESSAGE, MAX_MESSAGE_CHARS, embed_length

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
        if not embeds:
            raise DiscordError("refusing to post a message with no embeds")
        if len(embeds) > MAX_EMBEDS_PER_MESSAGE:
            raise DiscordError(f"{len(embeds)} embeds exceeds Discord's limit of {MAX_EMBEDS_PER_MESSAGE}")
        total = sum(embed_length(e) for e in embeds)
        if total > MAX_MESSAGE_CHARS:
            raise DiscordError(f"{total} characters exceeds Discord's per-message limit of {MAX_MESSAGE_CHARS}")
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
