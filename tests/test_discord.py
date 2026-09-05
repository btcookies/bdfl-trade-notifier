import json

import pytest
import requests
import responses

from bdfl.discord import DiscordError, DiscordPermanentError, DiscordWebhook

URL = "https://discord.com/api/webhooks/123/abc"
EMBED = {"title": "hi"}


@responses.activate
def test_post_sends_embeds_without_username_override_and_no_mentions():
    responses.post(URL, json={"id": "1"}, status=200)
    DiscordWebhook(URL, sleep=lambda s: None).post([EMBED])
    call = responses.calls[0]
    assert call.request.url == URL + "?wait=true"
    body = json.loads(call.request.body)
    assert body == {"embeds": [EMBED], "allowed_mentions": {"parse": []}}


@responses.activate
def test_post_includes_username_only_when_given():
    responses.post(URL, json={"id": "1"}, status=200)
    DiscordWebhook(URL, sleep=lambda s: None, username="Barbara Dodson").post([EMBED])
    assert json.loads(responses.calls[0].request.body)["username"] == "Barbara Dodson"


@responses.activate
def test_post_retries_once_after_429_using_retry_after():
    responses.post(URL, json={"retry_after": 3}, status=429, headers={"Retry-After": "3"})
    responses.post(URL, json={"id": "1"}, status=200)
    slept = []
    DiscordWebhook(URL, sleep=slept.append).post([EMBED])
    assert slept == [3.0]
    assert len(responses.calls) == 2


@responses.activate
def test_post_raises_after_second_429():
    responses.post(URL, status=429, headers={"Retry-After": "1"})
    responses.post(URL, status=429, headers={"Retry-After": "1"})
    slept = []
    with pytest.raises(DiscordError):
        DiscordWebhook(URL, sleep=slept.append).post([EMBED])
    assert len(responses.calls) == 2
    assert slept == [1.0]


@responses.activate
def test_post_raises_on_server_error_without_retry():
    responses.post(URL, status=502, body="bad gateway")
    with pytest.raises(DiscordError, match="502"):
        DiscordWebhook(URL, sleep=lambda s: None).post([EMBED])
    assert len(responses.calls) == 1


@responses.activate
def test_post_wraps_connection_errors():
    responses.post(URL, body=requests.exceptions.ConnectionError("boom"))
    with pytest.raises(DiscordError):
        DiscordWebhook(URL, sleep=lambda s: None).post([EMBED])


@responses.activate
def test_post_refuses_oversized_messages_without_sending():
    hook = DiscordWebhook(URL, sleep=lambda s: None)
    with pytest.raises(DiscordError, match="no embeds"):
        hook.post([])
    with pytest.raises(DiscordError, match="exceeds Discord's limit of 10"):
        hook.post([EMBED] * 11)
    with pytest.raises(DiscordError, match="per-message limit of 6000"):
        hook.post([{"title": "t", "description": "x" * 4000}, {"title": "t", "description": "x" * 2100}])
    assert len(responses.calls) == 0


@responses.activate
def test_long_retry_after_fails_fast_without_sleeping_or_retrying():
    responses.post(URL, status=429, headers={"Retry-After": "30"})
    slept = []
    with pytest.raises(DiscordError, match="rate limited for 30s"):
        DiscordWebhook(URL, sleep=slept.append).post([EMBED])
    assert slept == []
    assert len(responses.calls) == 1


@responses.activate
def test_retry_after_falls_back_to_json_body_then_one_second():
    responses.post(URL, status=429, json={"retry_after": 2.5})
    responses.post(URL, json={"id": "1"}, status=200)
    slept = []
    DiscordWebhook(URL, sleep=slept.append).post([EMBED])
    assert slept == [2.5]

    responses.reset()
    responses.post(URL, status=429, body="<html>cloudflare</html>")
    responses.post(URL, json={"id": "1"}, status=200)
    slept = []
    DiscordWebhook(URL, sleep=slept.append).post([EMBED])
    assert slept == [1.0]

    responses.reset()
    responses.post(URL, status=429, headers={"Retry-After": "nan"})
    responses.post(URL, json={"id": "1"}, status=200)
    slept = []
    DiscordWebhook(URL, sleep=slept.append).post([EMBED])
    assert slept == [1.0]


@responses.activate
def test_204_counts_as_success():
    responses.post(URL, status=204)
    DiscordWebhook(URL, sleep=lambda s: None).post([EMBED])
    assert len(responses.calls) == 1


@responses.activate
def test_400_is_permanent_and_5xx_is_transient():
    responses.post(URL, status=400, json={"message": "Invalid Form Body"})
    with pytest.raises(DiscordPermanentError, match="400"):
        DiscordWebhook(URL, sleep=lambda s: None).post([EMBED])
    responses.reset()
    responses.post(URL, status=503)
    with pytest.raises(DiscordError) as info:
        DiscordWebhook(URL, sleep=lambda s: None).post([EMBED])
    assert not isinstance(info.value, DiscordPermanentError)


@responses.activate
def test_validation_failures_are_permanent():
    hook = DiscordWebhook(URL, sleep=lambda s: None)
    with pytest.raises(DiscordPermanentError):
        hook.post([])
    with pytest.raises(DiscordPermanentError):
        hook.post([EMBED] * 11)


@responses.activate
def test_network_errors_never_include_the_webhook_url():
    responses.post(URL, body=requests.exceptions.ConnectTimeout("timed out"))
    with pytest.raises(DiscordError) as info:
        DiscordWebhook(URL, sleep=lambda s: None).post([EMBED])
    assert "abc" not in str(info.value)
    assert "webhooks" not in str(info.value)
    assert info.value.__cause__ is None
    assert info.value.__context__ is None
    import traceback

    rendered = "".join(traceback.format_exception(info.value))
    assert "abc" not in rendered and "webhooks" not in rendered
    assert "ConnectTimeout" in str(info.value)


@responses.activate
def test_uses_injected_session_and_timeout():
    session = requests.Session()
    seen = {}
    original = session.post

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return original(*args, **kwargs)

    session.post = spy
    responses.post(URL, json={"id": "1"}, status=200)
    DiscordWebhook(URL, session=session, sleep=lambda s: None).post([EMBED])
    assert seen["timeout"] == (3.05, 7.0)


@responses.activate
def test_retry_after_with_non_object_json_body_falls_back_to_one_second():
    responses.post(URL, status=429, json=["nope"])
    responses.post(URL, json={"id": "1"}, status=200)
    slept = []
    DiscordWebhook(URL, sleep=slept.append).post([EMBED])
    assert slept == [1.0]
