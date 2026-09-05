import json

import pytest
import responses

from bdfl.discord import DiscordError, DiscordWebhook

URL = "https://discord.com/api/webhooks/123/abc"
EMBED = {"title": "hi"}


@responses.activate
def test_post_sends_embeds_with_username_and_no_mentions():
    responses.post(URL, json={"id": "1"}, status=200)
    DiscordWebhook(URL, sleep=lambda s: None).post([EMBED])
    call = responses.calls[0]
    assert call.request.url == URL + "?wait=true"
    body = json.loads(call.request.body)
    assert body == {"username": "BDFL", "embeds": [EMBED], "allowed_mentions": {"parse": []}}


@responses.activate
def test_post_retries_once_after_429_using_retry_after_capped_at_five_seconds():
    responses.post(URL, json={"retry_after": 30}, status=429, headers={"Retry-After": "30"})
    responses.post(URL, json={"id": "1"}, status=200)
    slept = []
    DiscordWebhook(URL, sleep=slept.append).post([EMBED])
    assert slept == [5.0]
    assert len(responses.calls) == 2


@responses.activate
def test_post_raises_after_second_429():
    responses.post(URL, status=429, headers={"Retry-After": "1"})
    responses.post(URL, status=429, headers={"Retry-After": "1"})
    with pytest.raises(DiscordError):
        DiscordWebhook(URL, sleep=lambda s: None).post([EMBED])


@responses.activate
def test_post_raises_on_server_error_without_retry():
    responses.post(URL, status=502, body="bad gateway")
    with pytest.raises(DiscordError, match="502"):
        DiscordWebhook(URL, sleep=lambda s: None).post([EMBED])
    assert len(responses.calls) == 1


@responses.activate
def test_post_wraps_connection_errors():
    responses.post(URL, body=ConnectionError("boom"))
    with pytest.raises(DiscordError):
        DiscordWebhook(URL, sleep=lambda s: None).post([EMBED])
