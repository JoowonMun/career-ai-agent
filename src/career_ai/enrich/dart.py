"""DART 전자공시: 회사 찾기, 최근 사업보고서의 '사업의 내용'과 재무 요약."""

import functools
import html
import io
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, timedelta
from pathlib import Path

import httpx

from career_ai.http import get

API = "https://opendart.fss.or.kr/api"
REPORT_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={}"
CORP_CACHE = Path.home() / ".career-ai" / "cache" / "dart-corpcode.xml"
CORP_CACHE_DAYS = 30
MAX_CANDIDATES = 20
SECTION_MAX_CHARS = 3000
REPORT_LOOKBACK_DAYS = 730
ANNUAL_REPORT_CODE = "11011"
# '사업의 내용' 하위 절 중 매출 구성을 담는 절의 제목 키워드
REVENUE_KEYWORDS = ("주요 제품", "매출")


class DartError(Exception):
    """DART가 오류 상태를 돌려줬을 때. 메시지는 사용자에게 그대로 보여 준다."""


# DART는 'SK브로드밴드'를 '에스케이브로드밴드'처럼 영문 약자를 한글로 읽어 등록하는 경우가 많아,
# 비교할 때는 양쪽 영문을 모두 한글 읽기로 바꾼다.
_LETTERS = dict(zip(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    ["에이", "비", "씨", "디", "이", "에프", "지", "에이치", "아이", "제이", "케이", "엘", "엠",
     "엔", "오", "피", "큐", "알", "에스", "티", "유", "브이", "더블유", "엑스", "와이", "제트"],
    strict=True,
))


@functools.cache
def _normalize_name(name: str) -> str:
    name = re.sub(r"\(주\)|㈜|주식회사|\s", "", name)
    return re.sub(r"[A-Za-z]", lambda m: _LETTERS[m[0].upper()], name)


def parse_corp_codes(xml: bytes) -> list[dict]:
    corps = []
    for item in ET.fromstring(xml).iter("list"):
        stock = (item.findtext("stock_code") or "").strip()
        corps.append({
            "corp_code": item.findtext("corp_code"),
            "corp_name": item.findtext("corp_name"),
            "stock_code": stock or None,
        })
    return corps


def pick_corp(matches: list[dict], name: str) -> dict | None:
    """이름이 정확히 같은 회사가 하나뿐일 때만 그 회사. 일부만 일치하면 사람이 골라야 한다."""
    exact = [c for c in matches if _normalize_name(c["corp_name"]) == _normalize_name(name)]
    return exact[0] if len(matches) == 1 and len(exact) == 1 else None


def find_corp(corps: list[dict], name: str) -> list[dict]:
    """이름이 같은 회사가 있으면 그것만, 없으면 이름을 포함하는 회사. 상장사를 앞에 둔다."""
    query = _normalize_name(name)
    exact = [c for c in corps if _normalize_name(c["corp_name"]) == query]
    matches = exact or [c for c in corps if query in _normalize_name(c["corp_name"])]
    return sorted(matches, key=lambda c: c["stock_code"] is None)[:MAX_CANDIDATES]


def _unzip(content: bytes, prefer: str | None = None) -> bytes:
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        # 오류일 때는 zip 대신 <result><status/><message/></result> XML이 온다.
        root = ET.fromstring(content)
        raise DartError(f"{root.findtext('status')}: {root.findtext('message')}") from None
    names = zf.namelist()
    return zf.read(prefer if prefer in names else names[0])


def load_corp_codes(
    client: httpx.Client, key: str, cache: Path = CORP_CACHE, *, backoff: float = 1.0
) -> list[dict]:
    fresh = cache.exists() and time.time() - cache.stat().st_mtime < CORP_CACHE_DAYS * 86400
    if not fresh:
        response = get(client, f"{API}/corpCode.xml", params={"crtfc_key": key}, backoff=backoff)
        xml = _unzip(response.content)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(xml)
    # 회사 목록은 수십 MB라, 같은 실행 안에서는 한 번만 읽는다.
    stamp = (str(cache), cache.stat().st_mtime)
    if stamp not in _CORP_MEMO:
        _CORP_MEMO.clear()
        _CORP_MEMO[stamp] = parse_corp_codes(cache.read_bytes())
    return _CORP_MEMO[stamp]


_CORP_MEMO: dict[tuple[str, float], list[dict]] = {}


def _call(client: httpx.Client, path: str, params: dict, backoff: float) -> dict | None:
    """정상이면 응답, '조회된 데이터 없음'(013)이면 None."""
    data = get(client, f"{API}/{path}", params=params, backoff=backoff).json()
    if data["status"] == "013":
        return None
    if data["status"] != "000":
        raise DartError(f"{data['status']}: {data['message']}")
    return data


def _to_text(fragment: str) -> str:
    text = re.sub(r"</(TD|TH|TE|TU)>", "\x1f", fragment)
    text = re.sub(r"\x1f\s*</TR>", "\n", text)
    text = text.replace("\x1f", " | ")
    text = re.sub(r"</P>|<BR\s*/?>|</TITLE>|</TR>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    lines = (re.sub(r"[ \t\xa0]+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


_SECTION = r"<SECTION-{n}[^>]*>\s*<TITLE[^>]*>(.*?)</TITLE>(.*?)</SECTION-{n}>"


def parse_business(xml: str) -> dict:
    """사업보고서 본문에서 'II. 사업의 내용'의 하위 절을 사업 설명과 매출 구성으로 나눈다."""
    business, revenue_mix = [], []
    for title, body in re.findall(_SECTION.format(n=1), xml, re.DOTALL):
        if "사업의 내용" not in title:
            continue
        for sub_title, sub_body in re.findall(_SECTION.format(n=2), body, re.DOTALL):
            text = _to_text(sub_body)
            section = {
                "title": _to_text(sub_title),
                "text": text[:SECTION_MAX_CHARS],
                "truncated": len(text) > SECTION_MAX_CHARS,
            }
            is_revenue = any(k in section["title"] for k in REVENUE_KEYWORDS)
            (revenue_mix if is_revenue else business).append(section)
    return {"business": business, "revenue_mix": revenue_mix}


def _amount(raw: str | None) -> int | None:
    raw = (raw or "").replace(",", "").strip()
    return int(raw) if raw and raw != "-" else None


def parse_financials(items: list[dict]) -> dict:
    """주요 계정. 연결재무제표가 있으면 연결, 없으면 별도 재무제표."""
    fs_div = "CFS" if any(i["fs_div"] == "CFS" for i in items) else "OFS"
    rows = [i for i in items if i["fs_div"] == fs_div]
    year = int(rows[0]["bsns_year"])
    return {
        "statement": rows[0]["fs_nm"],
        "unit": rows[0].get("currency", "KRW"),
        "accounts": [
            {
                "account": r["account_nm"],
                str(year): _amount(r.get("thstrm_amount")),
                str(year - 1): _amount(r.get("frmtrm_amount")),
                str(year - 2): _amount(r.get("bfefrmtrm_amount")),
            }
            for r in rows
        ],
    }


def _decode(xml: bytes) -> str:
    try:
        return xml.decode("utf-8")
    except UnicodeDecodeError:
        return xml.decode("cp949")


def lookup(
    client: httpx.Client,
    key: str,
    cache: Path = CORP_CACHE,
    *,
    name: str | None = None,
    corp_code: str | None = None,
    backoff: float = 1.0,
) -> dict:
    """회사가 하나로 정해지면 개요·사업의 내용·재무, 아니면 {candidates}."""
    if corp_code is None:
        matches = find_corp(load_corp_codes(client, key, cache, backoff=backoff), name or "")
        picked = pick_corp(matches, name or "")
        if picked is None:
            return {"candidates": matches}
        corp_code = picked["corp_code"]

    params = {"crtfc_key": key, "corp_code": corp_code}
    overview = _call(client, "company.json", params, backoff)
    if overview:
        overview = {k: v for k, v in overview.items() if k not in ("status", "message")}
    result = {"corp_code": corp_code, "overview": overview, "report": None,
              "business": [], "revenue_mix": [], "financials": None}

    reports = _call(client, "list.json", {
        **params,
        "bgn_de": (date.today() - timedelta(days=REPORT_LOOKBACK_DAYS)).strftime("%Y%m%d"),
        "pblntf_detail_ty": "A001",
        "last_reprt_at": "Y",
        "page_count": 100,
    }, backoff)
    if not reports:
        return result
    latest = max(reports["list"], key=lambda r: r["rcept_no"])
    rcept_no = latest["rcept_no"]
    result["report"] = {"name": latest["report_nm"], "rcept_no": rcept_no,
                        "url": REPORT_URL.format(rcept_no)}

    document = get(client, f"{API}/document.xml",
                   params={"crtfc_key": key, "rcept_no": rcept_no}, backoff=backoff)
    result.update(parse_business(_decode(_unzip(document.content, f"{rcept_no}.xml"))))

    year = re.search(r"\((\d{4})\.\d{2}\)", latest["report_nm"])
    if year:
        fin = _call(client, "fnlttSinglAcnt.json", {
            **params, "bsns_year": year.group(1), "reprt_code": ANNUAL_REPORT_CODE,
        }, backoff)
        if fin:
            result["financials"] = parse_financials(fin["list"])
    return result


_TOTAL_LABELS = ("합계", "소계", "총계")


def _is_total(value: str | None) -> bool:
    value = (value or "").replace(" ", "")
    return value == "계" or any(label in value for label in _TOTAL_LABELS)


def parse_employees(rows: list[dict]) -> tuple[int | None, int | None]:
    """직원 현황 행에서 (직원 수, 1인 평균 급여 만원).

    부문·성별 합계 행이 섞여 있어 그대로 더하면 두 배가 된다. 우선순위:
    1. 부문·성별 모두 합계인 행 하나
    2. 합계 부문(예: 삼성전자의 '성별합계')의 남·여 행
    3. 합계·소계가 아닌 남·여 행 전부
    """
    grand = [r for r in rows if _is_total(r.get("fo_bbm")) and _is_total(r.get("sexdstn"))]
    total_division = [r for r in rows
                      if _is_total(r.get("fo_bbm")) and not _is_total(r.get("sexdstn"))]
    if grand:
        rows = grand[:1]
    elif total_division:
        rows = total_division
    else:
        rows = [r for r in rows
                if not _is_total(r.get("fo_bbm")) and not _is_total(r.get("sexdstn"))]
    employees = sum(_amount(r.get("sm")) or 0 for r in rows)
    salary = sum(_amount(r.get("fyer_salary_totamt")) or 0 for r in rows)
    if not employees:
        return None, None
    return employees, round(salary / employees / 10000) if salary else None


def employee_rows(client: httpx.Client, key: str, corp_code: str, year: int,
                  *, backoff: float = 1.0) -> list[dict] | None:
    data = _call(client, "empSttus.json", {
        "crtfc_key": key, "corp_code": corp_code, "bsns_year": str(year),
        "reprt_code": ANNUAL_REPORT_CODE,
    }, backoff)
    return data["list"] if data else None


def overview(client: httpx.Client, key: str, corp_code: str, *, backoff: float = 1.0) -> dict:
    return _call(client, "company.json", {"crtfc_key": key, "corp_code": corp_code}, backoff) or {}
