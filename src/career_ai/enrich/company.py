"""기업 규모 정보: DART 직원 현황, 없으면 국민연금 가입자 수. companies/에 90일 캐시."""

import json
import re
from datetime import date
from pathlib import Path

import httpx

from career_ai.enrich import dart, nps
from career_ai.enrich.news import months_ago

CACHE_DAYS = 90
# 규모 구분 기준(직원 수). 법적 기준(자산·매출)이 아니라 직원 수로 단순하게 나눈다.
LARGE_MIN_EMPLOYEES = 1000
MID_MIN_EMPLOYEES = 300
STARTUP_MAX_YEARS = 7
LISTED_CLASSES = ("Y", "K", "N")  # 유가증권, 코스닥, 코넥스


def classify(employees: int | None, founded: date | None, today: date) -> str | None:
    if employees is None:
        return None
    if employees >= LARGE_MIN_EMPLOYEES:
        return "대기업"
    if employees >= MID_MIN_EMPLOYEES:
        return "중견기업"
    if founded and founded >= months_ago(today, STARTUP_MAX_YEARS * 12):
        return "스타트업"
    return "중소기업"


def cache_path(cache_dir: Path, name: str) -> Path:
    return cache_dir / f"{re.sub(r'[\\/:*?\"<>|\s]', '', name)}.json"


def _iso(yyyymmdd: str | None) -> str | None:
    d = yyyymmdd or ""
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 and d.isdigit() else None


def _from_dart(client, key, name, corp_code, info, today, corp_cache, backoff) -> dict | None:
    """정보를 info에 채운다. 후보가 여러 개면 candidates를 돌려준다."""
    if corp_code is None:
        matches = dart.find_corp(dart.load_corp_codes(client, key, corp_cache, backoff=backoff),
                                 name)
        if not matches:
            # 공고 회사명과 DART 등록명이 다를 수 있어(네이버/NAVER) 비상장으로 단정하지 않는다.
            return None
        picked = dart.pick_corp(matches, name)
        if picked is None:
            return {"source": "DART", "items": matches}
        corp_code = picked["corp_code"]
    overview = dart.overview(client, key, corp_code, backoff=backoff)
    info["listed"] = overview.get("corp_cls") in LISTED_CLASSES
    info["founded"] = _iso(overview.get("est_dt"))
    for year in (today.year - 1, today.year - 2):
        rows = dart.employee_rows(client, key, corp_code, year, backoff=backoff)
        if rows:
            info["employees"], info["avg_salary_10k_krw"] = dart.parse_employees(rows)
            info["sources"].append(f"DART {year} 사업보고서")
            break
    return None


def _from_nps(client, key, name, nps_seq, info, backoff) -> dict | None:
    if nps_seq is None:
        workplaces = nps.search(client, key, name, backoff=backoff)
        matches = nps.find(workplaces, name)
        if len(matches) > 1:
            return {"source": "국민연금", "items": matches}
        if not matches:
            return None
        nps_seq = matches[0]["seq"]
        month = matches[0]["data_month"] or ""
        info["sources"].append(f"국민연금 가입 사업장 {month[:4]}-{month[4:]}")
    else:
        info["sources"].append("국민연금 가입 사업장")
    found = nps.detail(client, key, nps_seq, backoff=backoff)
    info["employees"] = found["employees"]
    # 국민연금 적용일을 설립일 대신 쓴다(스타트업 구분용).
    info["founded"] = info["founded"] or found["adopted"]
    return None


def lookup(
    client: httpx.Client,
    keys: dict[str, str],
    name: str,
    cache_dir: Path,
    *,
    corp_code: str | None = None,
    nps_seq: str | None = None,
    today: date | None = None,
    corp_cache: Path = dart.CORP_CACHE,
    backoff: float = 1.0,
) -> dict:
    today = today or date.today()
    path = cache_path(cache_dir, name)
    if path.exists() and corp_code is None and nps_seq is None:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if (today - date.fromisoformat(cached["fetched"])).days < CACHE_DAYS:
            return {**cached, "cached": True}

    info = {"name": name, "listed": None, "size": None, "employees": None,
            "avg_salary_10k_krw": None, "founded": None, "sources": [], "errors": [],
            "fetched": today.isoformat()}
    steps = (
        ("DART_API_KEY",
         lambda key: _from_dart(client, key, name, corp_code, info, today, corp_cache, backoff)),
        ("DATA_GO_KR_API_KEY",
         lambda key: _from_nps(client, key, name, nps_seq, info, backoff)),
    )
    for key_name, step in steps:
        if info["employees"] is not None:
            break
        if not keys.get(key_name):
            info["errors"].append(f"{key_name} 없음")
            continue
        try:
            candidates = step(keys[key_name])
        except Exception as e:  # noqa: BLE001 — 한 회사 조회 실패가 전체 filter를 멈추면 안 된다
            info["errors"].append(f"{type(e).__name__}: {e}")
            continue
        if candidates:
            return {"name": name, "candidates": candidates}

    founded = date.fromisoformat(info["founded"]) if info["founded"] else None
    info["size"] = classify(info["employees"], founded, today)
    if info["sources"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    return info
