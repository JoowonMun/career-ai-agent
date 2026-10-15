import json
from datetime import date
from pathlib import Path

import httpx

from career_ai.enrich import news

FIXTURE = Path(__file__).parent / "fixtures" / "naver" / "news.json"
TODAY = date(2026, 10, 13)


def test_parse_news_cleans_dedups_and_filters_by_date():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert news.parse_news(data, cutoff=date(2026, 4, 13)) == [
        {
            "title": '삼성전자, 사내 "생성형 AI" 전면 도입',
            "url": "https://news.example.com/a1",
            "date": "2026-10-10",
            "summary": "삼성전자가 업무 전반에 생성형 AI를 도입한다.",
        },
        {
            "title": "삼성전자 데이터센터 투자 확대",
            "url": "https://n.news.naver.com/a2",
            "date": "2026-04-15",
            "summary": "데이터센터 & 클라우드 투자",
        },
    ]


def test_months_ago_clamps_day():
    assert news.months_ago(date(2026, 8, 31), 6) == date(2026, 2, 28)
    assert news.months_ago(TODAY, 6) == date(2026, 4, 13)


def test_search_news_sends_keys_and_query():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=FIXTURE.read_bytes())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        items = news.search_news(client, "ID", "SECRET", "삼성전자 AI", today=TODAY, backoff=0)
    assert len(items) == 2
    [request] = seen
    assert request.headers["X-Naver-Client-Id"] == "ID"
    assert request.headers["X-Naver-Client-Secret"] == "SECRET"
    assert request.url.params["query"] == "삼성전자 AI"
    assert request.url.params["display"] == "100"


GOOGLE = Path(__file__).parent / "fixtures" / "google" / "news.xml"


def test_parse_google_news_strips_source_and_filters_by_date():
    items = news.parse_google_news(GOOGLE.read_bytes(), cutoff=date(2026, 10, 14))
    assert len(items) == 2
    first = items[0]
    assert first["source"] and not first["title"].endswith(f" - {first['source']}")
    assert first["url"].startswith("https://news.google.com/")
    assert first["date"] == "2026-10-14"


def test_search_google_news_sends_korean_feed_params():
    seen = {}

    def handler(request):
        seen.update(request.url.params)
        return httpx.Response(200, content=GOOGLE.read_bytes())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        items = news.search_google_news(client, "삼성전자", today=date(2026, 10, 14), backoff=0)
    assert seen == {"q": "삼성전자", "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    assert len(items) == 3
