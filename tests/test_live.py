"""실제 API 호출 확인. 저장해 둔 fixture 형식이 실제 응답과 같은지 볼 때 직접 돌린다.

uv run pytest -m live
"""

import httpx
import pytest

from career_ai.config import ConfigError, api_keys
from career_ai.enrich import dart, news

pytestmark = pytest.mark.live


def keys(*names: str) -> tuple[str, ...]:
    try:
        return api_keys(names)
    except ConfigError as e:
        pytest.skip(str(e))


def test_dart_samsung(tmp_path):
    (key,) = keys("DART_API_KEY")
    with httpx.Client(timeout=60) as client:
        result = dart.lookup(client, key, tmp_path / "corpcode.xml", name="삼성전자")
    assert result["corp_code"] == "00126380"
    assert result["report"] and result["business"]
    assert result["financials"]["accounts"]


def test_naver_news():
    client_id, secret = keys("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET")
    with httpx.Client(timeout=30) as client:
        items = news.search_news(client, client_id, secret, "삼성전자 AI")
    assert items and {"title", "url", "date", "summary"} <= items[0].keys()


def test_saramin_and_work24_search():
    from career_ai.search import search

    found = {}
    for name in ("SARAMIN_API_KEY", "WORK24_API_KEY"):
        found.update(dict(zip((name,), keys(name), strict=True)))
    with httpx.Client(timeout=30) as client:
        result = search(client, ["데이터 분석"], found)
    assert result["skipped"] == []
    assert {p["platform"] for p in result["postings"]} == {"사람인", "고용24"}


def test_company_size_from_dart_and_nps(tmp_path):
    from career_ai.enrich import company

    found = dict(zip(("DART_API_KEY", "DATA_GO_KR_API_KEY"),
                     keys("DART_API_KEY", "DATA_GO_KR_API_KEY"), strict=True))
    with httpx.Client(timeout=60) as client:
        listed = company.lookup(client, found, "삼성전자", tmp_path, corp_cache=tmp_path / "c.xml")
        # DART 키 없이 국민연금만으로
        unlisted = company.lookup(client, {"DATA_GO_KR_API_KEY": found["DATA_GO_KR_API_KEY"]},
                                  "우아한형제들", tmp_path / "nps")
    assert listed["size"] == "대기업" and listed["listed"] is True
    assert listed["avg_salary_10k_krw"]
    assert unlisted.get("candidates") or unlisted["employees"]


def test_google_news_without_key():
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        items = news.search_google_news(client, "삼성전자")
    assert items and items[0]["source"] and items[0]["url"].startswith("https://")
