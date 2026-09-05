"""Minimal Discord webhook client."""

from __future__ import annotations

import math
import time
from collections.abc import Callable

import requests

from bdfl.messages import MAX_EMBEDS_PER_MESSAGE, MAX_MESSAGE_CHARS, embed_length

MAX_RETRY_AFTER_SECONDS = 5.0


class DiscordError(Exception):
    pass


class DiscordPermanentError(DiscordError):
    """The message can never be delivered as-is; do not retry."""


class DiscordWebhook:
    """Posts embeds to a single Discord channel webhook."""

    def __init__(
        self,
        url: str,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        username: str = "BDFL",
        timeout: float | tuple[float, float] = (3.05, 7.0),
    ) -> None:
        self.url = url
        self.session = session or requests.Session()
        self.sleep = sleep
        self.username = username
        self.timeout = timeout

    def post(self, embeds: list[dict]) -> None:
        """Post the embeds as one message, retrying once inside a short rate-limit window."""
        if not embeds:
            raise DiscordPermanentError("refusing to post a message with no embeds")
        if len(embeds) > MAX_EMBEDS_PER_MESSAGE:
            raise DiscordPermanentError(
                f"{len(embeds)} embeds exceeds Discord's limit of {MAX_EMBEDS_PER_MESSAGE}"
            )
        total = sum(embed_length(e) for e in embeds)
        if total > MAX_MESSAGE_CHARS:
            raise DiscordPermanentError(
                f"{total} characters exceeds Discord's per-message limit of {MAX_MESSAGE_CHARS}"
            )
        body = {"username": self.username, "embeds": embeds, "allowed_mentions": {"parse": []}}
        response = self._send(body)
        if response.status_code == 429:
            delay = self._retry_after(response)
            if delay > MAX_RETRY_AFTER_SECONDS:
                # Longer than the Lambda can wait; the next poll picks the message back up.
                raise DiscordError(f"Discord rate limited for {delay:.0f}s; retrying on the next poll")
            self.sleep(delay)
            response = self._send(body)
        if not 200 <= response.status_code < 300:
            excerpt = response.content[:200].decode("utf-8", "replace")
            message = f"Discord webhook returned {response.status_code}: {excerpt}"
            if 400 <= response.status_code < 500 and response.status_code != 429:
                raise DiscordPermanentError(message)
            raise DiscordError(message)

    def _send(self, body: dict) -> requests.Response:
        try:
            return self.session.post(
                self.url, params={"wait": "true"}, json=body, timeout=self.timeout
            )
        except requests.RequestException as exc:
            # requests puts the full URL, including the webhook token, in its messages.
            raise DiscordError(f"Discord request failed: {type(exc).__name__}") from None

    @staticmethod
    def _retry_after(response: requests.Response) -> float:
        raw = response.headers.get("Retry-After")
        if raw is None:
            try:
                raw = response.json().get("retry_after")
            except (ValueError, AttributeError):  # a Cloudflare 429 is HTML, not a JSON object
                raw = None
        try:
            seconds = float(raw)
        except (TypeError, ValueError):
            seconds = 1.0
        if not math.isfinite(seconds):
            seconds = 1.0
        return max(seconds, 0.0)
