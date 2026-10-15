"""preferences.yaml의 필수 조건으로 공고를 거른다. 판단할 정보가 없으면 탈락시키지 않고 unknown."""

import re
from collections.abc import Callable
from pathlib import Path

import yaml


def load_preferences(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}


def _normalize(name: str) -> str:
    return re.sub(r"\(주\)|㈜|주식회사|\s", "", name)


def _region_ok(location: str, regions: list[str]) -> bool:
    if "전국" in location:
        return True
    return any(all(token in location for token in region.split()) for region in regions)


def _employment_ok(value: str, types: list[str]) -> bool:
    """'정규직,계약직'처럼 여러 개면 하나라도 정확히 일치하면 통과.

    '계약직 (정규직 전환가능)'은 정규직이 아니다.
    """
    offered = {part.strip() for part in value.split(",")}
    return any(t in offered for t in types)


def _check(p: dict, prefs: dict) -> tuple[list[str], list[str]]:
    hard = prefs.get("hard") or {}
    reasons, unknown = [], []

    excluded = {_normalize(c) for c in hard.get("exclude_companies") or []}
    if _normalize(p["company"]) in excluded:
        reasons.append("제외 기업")
    for keyword in prefs.get("keywords_exclude") or []:
        if keyword in p["title"]:
            reasons.append(f"제외 키워드: {keyword}")

    if types := hard.get("employment_types"):
        if not p.get("employment_type"):
            unknown.append("고용 형태")
        elif not _employment_ok(p["employment_type"], types):
            reasons.append(f"고용 형태: {p['employment_type']}")

    regions = hard.get("regions")
    remote_ok = p.get("remote") and hard.get("remote_ignores_region")
    if regions and not remote_ok:
        if not p.get("location"):
            unknown.append("지역")
        elif not _region_ok(p["location"], regions):
            reasons.append(f"지역: {p['location']}")

    if minimum := hard.get("min_salary_10k_krw"):
        high, low = p.get("salary_max_10k_krw"), p.get("salary_min_10k_krw")
        if high is not None and high < minimum:
            reasons.append(f"연봉 상한 {high}만원 < {minimum}만원")
        elif high is None and low is None:
            unknown.append("연봉")
    return reasons, unknown


def _size_check(info: dict | None, sizes: list[str]) -> tuple[str | None, bool]:
    """(탈락 이유, 정보 없음 여부)."""
    if not info or "candidates" in info:
        return None, True
    if info.get("listed") and "상장사" in sizes:
        return None, False
    if info.get("size") is None:
        return None, True
    if info["size"] in sizes:
        return None, False
    return f"기업 규모: {info['size']}", False


def apply(postings: list[dict], prefs: dict,
          company_info: Callable[[str], dict | None]) -> dict:
    """기업 정보 조회는 다른 조건을 통과한 공고에만 한다."""
    sizes = (prefs.get("hard") or {}).get("company_size")
    passed, rejected = [], []
    for p in postings:
        reasons, unknown = _check(p, prefs)
        info = None
        if not reasons and sizes:
            info = company_info(p["company"])
            reason, is_unknown = _size_check(info, sizes)
            if reason:
                reasons.append(reason)
            if is_unknown:
                unknown.append("기업 규모")
        if reasons:
            rejected.append({"posting_id": p["posting_id"], "company": p["company"],
                             "title": p["title"], "reasons": reasons})
        else:
            passed.append({**p, "company_info": info, "unknown": unknown})
    return {"passed": passed, "rejected": rejected}
