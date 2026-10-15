"""뉴스 검색: 최근 N개월 기사 제목·링크·요약.

네이버 검색 API 키가 있으면 네이버, 없으면 구글 뉴스 RSS(키 불필요, 개인적 사용만 허용)를 쓴다.
"""

import calendar
import html
import re
import xml.etree.ElementTree as ET
from datetime import date
from email.utils import parsedate_to_datetime

import httpx

from career_ai.http import get

API = "https://openapi.naver.com/v1/search/news.json"
DISPLAY = 100  # 네이버 API의 한 번 최대 개수
GOOGLE_RSS = "https://news.google.com/rss/search"
# 구글 뉴스 RSS는 'when:6m' 같은 기간 조건을 주면 결과가 비어서, 날짜는 받은 뒤 거른다.
GOOGLE_PARAMS = {"hl": "ko", "gl": "KR", "ceid": "KR:ko"}


def months_ago(today: date, months: int) -> date:
    month_index = today.year * 12 + today.month - 1 - months
    year, month = divmod(month_index, 12)
    day = min(today.day, calendar.monthrange(year, month + 1)[1])
    return date(year, month + 1, day)


def _clean(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def parse_news(data: dict, cutoff: date) -> list[dict]:
    items, seen = [], set()
    for item in data["items"]:
        title = _clean(item["title"])
        published = parsedate_to_datetime(item["pubDate"]).date()
        if published < cutoff or title in seen:
            continue
        seen.add(title)
        items.append({
            "title": title,
            "url": item["originallink"] or item["link"],
            "date": published.isoformat(),
            "summary": _clean(item["description"]),
        })
    return items


def search_news(
    client: httpx.Client,
    client_id: str,
    client_secret: str,
    query: str,
    *,
    months: int = 6,
    today: date | None = None,
    backoff: float = 1.0,
) -> list[dict]:
    """관련도순 상위 100건 중 최근 N개월 기사."""
    response = get(
        client,
        API,
        params={"query": query, "display": DISPLAY, "sort": "sim"},
        headers={"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret},
        backoff=backoff,
    )
    return parse_news(response.json(), months_ago(today or date.today(), months))


def parse_google_news(xml: bytes, cutoff: date) -> list[dict]:
    """구글 뉴스 RSS. 제목 끝의 ' - 언론사'는 떼고 언론사는 source에 둔다."""
    items, seen = [], set()
    for item in ET.fromstring(xml).iter("item"):
        source = (item.findtext("source") or "").strip()
        title = (item.findtext("title") or "").strip()
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        published = parsedate_to_datetime(item.findtext("pubDate") or "").date()
        if not title or published < cutoff or title in seen:
            continue
        seen.add(title)
        items.append({
            "title": title,
            "url": (item.findtext("link") or "").strip(),
            "date": published.isoformat(),
            "summary": "",
            "source": source,
        })
    return items


def search_google_news(
    client: httpx.Client,
    query: str,
    *,
    months: int = 6,
    today: date | None = None,
    backoff: float = 1.0,
) -> list[dict]:
    response = get(client, GOOGLE_RSS, params={"q": query, **GOOGLE_PARAMS}, backoff=backoff)
    return parse_google_news(response.content, months_ago(today or date.today(), months))
