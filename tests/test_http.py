import httpx
import pytest

from career_ai.http import get


def flaky(statuses: list[int]):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(statuses[len(calls) - 1], text="body")

    return handler, calls


def test_retries_server_errors_then_succeeds():
    handler, calls = flaky([500, 429, 200])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert get(client, "https://x.test/", backoff=0).status_code == 200
    assert len(calls) == 3


def test_gives_up_after_two_retries():
    handler, calls = flaky([503, 503, 503, 200])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            get(client, "https://x.test/", backoff=0)
    assert len(calls) == 3


def test_client_error_is_not_retried():
    handler, calls = flaky([401])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            get(client, "https://x.test/", backoff=0)
    assert len(calls) == 1


def test_network_error_is_retried():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("down")
        return httpx.Response(200)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert get(client, "https://x.test/", backoff=0).status_code == 200
