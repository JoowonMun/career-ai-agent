"""Notion REST API 최소 클라이언트. 이 도구가 쓰는 엔드포인트만 감싼다."""

import time
from collections.abc import Callable

import httpx

API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"
MAX_RETRIES = 2
# 요청 과다·과부하는 처리되지 않은 요청이라 어떤 요청이든 다시 보내도 된다.
_RATE_LIMITED = {429, 529}
# 서버 오류는 처리됐을 수도 있어서, 다시 보내도 결과가 같은 요청만 다시 보낸다.
_SERVER_ERRORS = {500, 502, 503, 504}
_IDEMPOTENT = {"GET", "DELETE"}


class NotionError(Exception):
    """Notion API 오류. 메시지는 사용자에게 그대로 보여 준다."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    try:
        return float(response.headers.get("Retry-After", ""))
    except ValueError:
        return float(attempt + 1)


class NotionClient:
    def __init__(
        self,
        token: str,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._http = httpx.Client(
            base_url=API_URL,
            headers={"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION},
            transport=transport,
            timeout=30,
        )
        self._sleep = sleep

    def _request(self, method: str, path: str, json: dict | None = None,
                 params: dict | None = None) -> dict:
        for attempt in range(MAX_RETRIES + 1):
            last = attempt == MAX_RETRIES
            try:
                response = self._http.request(method, path, json=json, params=params)
            except httpx.TransportError as e:
                if method in _IDEMPOTENT and not last:
                    self._sleep(attempt + 1)
                    continue
                raise NotionError(f"Notion에 연결하지 못했습니다: {e}") from e
            status = response.status_code
            retry = status in _RATE_LIMITED or (status in _SERVER_ERRORS and method in _IDEMPOTENT)
            if retry and not last:
                self._sleep(_retry_delay(response, attempt))
                continue
            break
        if response.is_error:
            try:
                body = response.json()
            except ValueError:
                body = {}
            code, message = body.get("code", ""), body.get("message", response.text)
            raise NotionError(f"Notion API {response.status_code} {code}: {message}",
                              status=response.status_code)
        return response.json()

    def create_database(self, parent_page_id: str, title: str, properties: dict) -> dict:
        database = self._request("POST", "/databases", json={
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            # 하위 페이지가 아니라 부모 페이지 안에 표로 바로 보이게 한다.
            "is_inline": True,
            "initial_data_source": {"properties": properties},
        })
        if "data_sources" not in database:
            database = self._request("GET", f"/databases/{database['id']}")
        return database

    def find_page(self, data_source_id: str, prop: str, value: str) -> dict | None:
        result = self._request("POST", f"/data_sources/{data_source_id}/query", json={
            "filter": {"property": prop, "rich_text": {"equals": value}},
            "page_size": 1,
        })
        return result["results"][0] if result["results"] else None

    def create_page(self, data_source_id: str, properties: dict) -> dict:
        return self._request("POST", "/pages", json={
            "parent": {"type": "data_source_id", "data_source_id": data_source_id},
            "properties": properties,
        })

    def update_page(self, page_id: str, properties: dict) -> dict:
        return self._request("PATCH", f"/pages/{page_id}", json={"properties": properties})

    def list_children(self, block_id: str) -> list[dict]:
        blocks, cursor = [], None
        while True:
            params = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            result = self._request("GET", f"/blocks/{block_id}/children", params=params)
            blocks.extend(result["results"])
            if not result.get("has_more"):
                return blocks
            cursor = result["next_cursor"]

    def append_children(self, block_id: str, children: list[dict],
                        position: dict | None = None) -> list[dict]:
        body: dict = {"children": children}
        if position:
            body["position"] = position
        return self._request("PATCH", f"/blocks/{block_id}/children", json=body)["results"]

    def delete_block(self, block_id: str) -> None:
        self._request("DELETE", f"/blocks/{block_id}")
