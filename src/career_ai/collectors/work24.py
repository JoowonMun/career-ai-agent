"""고용24 채용정보 API (구 워크넷 OpenAPI). 응답은 XML."""

import re
import xml.etree.ElementTree as ET
from datetime import date

import httpx

from career_ai.collectors import is_remote, parse_salary
from career_ai.http import get
from career_ai.models import Posting

API = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do"
DISPLAY = 100
# empTpCd: 10·11 기간의 정함이 없는 근로계약, 20·21 기간의 정함이 있는 근로계약, 4 파견
EMPLOYMENT_TYPES = {"10": "정규직", "11": "정규직", "20": "계약직", "21": "계약직", "4": "파견직"}
_YYMMDD = re.compile(r"(\d{2})-(\d{2})-(\d{2})")


def _date(text: str | None) -> str | None:
    match = _YYMMDD.search(text or "")
    return f"20{match[1]}-{match[2]}-{match[3]}" if match else None


def parse(xml: bytes) -> list[Posting]:
    root = ET.fromstring(xml)
    if root.tag != "wantedRoot":
        raise ValueError(f"고용24 응답 오류: {ET.tostring(root, encoding='unicode')[:300]}")
    postings = []
    for w in root.iter("wanted"):
        text = lambda tag, w=w: (w.findtext(tag) or "").strip() or None  # noqa: E731
        if not text("company") or not text("title") or not text("wantedAuthNo"):
            continue  # 필수 값이 빠진 공고 하나 때문에 전체를 버리지 않는다
        # 월급·시급은 연봉으로 환산하지 않는다.
        low, high = parse_salary(text("sal")) if text("salTpNm") == "연봉" else (None, None)
        postings.append(Posting(
            posting_id=f"work24-{text('wantedAuthNo')}",
            platform="고용24",
            company=text("company"),
            title=text("title"),
            url=text("wantedInfoUrl"),
            location=text("region"),
            remote=is_remote(text("title"), text("region")),
            employment_type=EMPLOYMENT_TYPES.get(text("empTpCd") or ""),
            experience=text("career"),
            industry=text("indTpNm"),
            salary=text("sal"),
            salary_min_10k_krw=low,
            salary_max_10k_krw=high,
            posted=_date(text("regDt")),
            deadline=_date(text("closeDt")),
        ))
    return postings


def search(client: httpx.Client, key: str, keywords: str, since: date | None,
           *, backoff: float = 1.0) -> list[Posting]:
    params = {"authKey": key, "callTp": "L", "returnType": "XML", "startPage": 1,
              "display": DISPLAY, "keyword": keywords}
    return parse(get(client, API, params=params, backoff=backoff).content)
