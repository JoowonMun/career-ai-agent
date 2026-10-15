"""외부 API 호출 공통 규칙: 실패하면 지수 백오프로 2번까지 다시 시도한다."""

import time

import httpx

RETRIES = 2


def _retryable(response: httpx.Response) -> bool:
    return response.status_code == 429 or response.status_code >= 500


def get(
    client: httpx.Client,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    backoff: float = 1.0,
) -> httpx.Response:
    for attempt in range(RETRIES + 1):
        last = attempt == RETRIES
        try:
            response = client.get(url, params=params, headers=headers)
        except httpx.TransportError:
            if last:
                raise
        else:
            if last or not _retryable(response):
                return response.raise_for_status()
        time.sleep(backoff * 2**attempt)
    raise AssertionError("unreachable")
