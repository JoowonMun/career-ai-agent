import json

import httpx
import pytest

from career_ai.notion_api import NOTION_VERSION, NotionClient, NotionError


def make_client(handler, sleeps=None):
    sleeps = sleeps if sleeps is not None else []
    return NotionClient("secret", transport=httpx.MockTransport(handler), sleep=sleeps.append)


def test_sends_auth_and_version_headers():
    seen = {}

    def handler(request):
        seen.update(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "p1", "url": "https://notion.so/p1"})

    page = make_client(handler).create_page("ds1", {"이름": {"title": []}})
    assert page["id"] == "p1"
    assert seen["authorization"] == "Bearer secret"
    assert seen["notion-version"] == NOTION_VERSION
    assert seen["body"]["parent"] == {"type": "data_source_id", "data_source_id": "ds1"}


def test_retries_on_429_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429, headers={"Retry-After": "0.5"}, json={})
        return httpx.Response(200, json={"id": "p1"})

    sleeps = []
    make_client(handler, sleeps).update_page("p1", {})
    assert len(calls) == 3
    assert sleeps == [0.5, 0.5]


def test_overload_529_is_retried_and_bad_retry_after_falls_back():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(529, headers={"Retry-After": "soon"}, json={})
        return httpx.Response(200, json={"id": "p1"})

    sleeps = []
    make_client(handler, sleeps).update_page("p1", {})
    assert sleeps == [1.0]


def test_server_error_on_create_is_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(500, json={"code": "internal_server_error", "message": "oops"})

    with pytest.raises(NotionError) as error:
        make_client(handler).create_page("ds1", {})
    assert len(calls) == 1
    assert error.value.status == 500


def test_network_error_becomes_notion_error_after_retries():
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ConnectError("offline")

    with pytest.raises(NotionError, match="연결"):
        make_client(handler).list_children("p1")
    assert len(calls) == 3


def test_error_message_includes_code():
    def handler(request):
        return httpx.Response(400, json={"code": "validation_error", "message": "bad property"})

    with pytest.raises(NotionError, match="400 validation_error: bad property"):
        make_client(handler).update_page("p1", {})


def test_list_children_follows_cursor():
    def handler(request):
        cursor = request.url.params.get("start_cursor")
        if cursor is None:
            return httpx.Response(200, json={"results": [{"id": "a"}], "has_more": True,
                                             "next_cursor": "c2"})
        return httpx.Response(200, json={"results": [{"id": "b"}], "has_more": False,
                                         "next_cursor": None})

    assert [b["id"] for b in make_client(handler).list_children("p1")] == ["a", "b"]


def test_find_page_filters_by_rich_text():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"results": [], "has_more": False})

    assert make_client(handler).find_page("ds1", "공고ID", "S001") is None
    assert seen["path"] == "/v1/data_sources/ds1/query"
    assert seen["body"]["filter"] == {"property": "공고ID", "rich_text": {"equals": "S001"}}


def test_create_database_is_inline_on_parent_page():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "db1", "data_sources": [{"id": "ds1"}]})

    make_client(handler).create_database("parent", "지원 현황", {})
    assert seen["body"]["is_inline"] is True


def test_create_database_reads_data_sources_when_partial():
    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"object": "database", "id": "db1"})
        return httpx.Response(200, json={"id": "db1", "data_sources": [{"id": "ds1"}]})

    db = make_client(handler).create_database("parent", "지원 현황", {})
    assert db["data_sources"][0]["id"] == "ds1"
