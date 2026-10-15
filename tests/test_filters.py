from pathlib import Path

import pytest

from career_ai import filters

PREFS = {
    "keywords_exclude": ["영업", "강사"],
    "hard": {
        "regions": ["서울", "경기 성남"],
        "remote_ignores_region": True,
        "employment_types": ["정규직"],
        "company_size": ["대기업", "중견기업", "상장사"],
        "min_salary_10k_krw": 5000,
        "exclude_companies": ["(주)싫은회사"],
    },
}
BIG = {"size": "대기업", "listed": True}


def posting(**overrides) -> dict:
    base = {
        "posting_id": "saramin-1", "company": "한빛데이터", "title": "LLM 엔지니어",
        "location": "서울 > 강남구", "remote": False, "employment_type": "정규직",
        "salary_min_10k_krw": 5000, "salary_max_10k_krw": 6000,
    }
    return {**base, **overrides}


def check(p: dict, info: dict | None = BIG, prefs: dict = PREFS):
    result = filters.apply([p], prefs, lambda name: info)
    if result["passed"]:
        return "passed", result["passed"][0]["unknown"]
    return "rejected", result["rejected"][0]["reasons"]


def test_all_conditions_met():
    assert check(posting()) == ("passed", [])


def test_passed_posting_carries_company_info():
    result = filters.apply([posting()], PREFS, lambda name: BIG)
    assert result["passed"][0]["company_info"] == BIG


@pytest.mark.parametrize(("overrides", "reason"), [
    ({"company": "싫은회사"}, "제외 기업"),
    ({"title": "AI 솔루션 영업"}, "제외 키워드: 영업"),
    ({"employment_type": "계약직"}, "고용 형태: 계약직"),
    ({"location": "부산 > 해운대구"}, "지역: 부산 > 해운대구"),
    ({"location": "경기 > 수원시"}, "지역: 경기 > 수원시"),
    ({"salary_max_10k_krw": 4999}, "연봉 상한 4999만원 < 5000만원"),
])
def test_rejections(overrides, reason):
    assert check(posting(**overrides)) == ("rejected", [reason])


def test_multiple_reasons_are_all_listed():
    status, reasons = check(posting(employment_type="계약직", location="부산"))
    assert status == "rejected" and len(reasons) == 2


@pytest.mark.parametrize("location", ["경기 > 성남시 분당구", "서울 > 강남구,부산 > 중구",
                                      "경기 성남시"])
def test_region_matches(location):
    assert check(posting(location=location)) == ("passed", [])


def test_remote_ignores_region():
    assert check(posting(location="부산", remote=True)) == ("passed", [])
    no_ignore = {**PREFS, "hard": {**PREFS["hard"], "remote_ignores_region": False}}
    assert check(posting(location="부산", remote=True), prefs=no_ignore)[0] == "rejected"


def test_salary_boundaries():
    assert check(posting(salary_max_10k_krw=5000)) == ("passed", [])
    # 'N만원 이상'처럼 상한이 없으면 통과
    assert check(posting(salary_min_10k_krw=3000, salary_max_10k_krw=None)) == ("passed", [])


def test_missing_information_is_unknown_not_rejected():
    p = posting(location=None, employment_type=None, salary_min_10k_krw=None,
                salary_max_10k_krw=None)
    assert check(p, info={"size": None, "listed": None}) == (
        "passed", ["고용 형태", "지역", "연봉", "기업 규모"])


def test_company_candidates_are_unknown():
    assert check(posting(), info={"name": "x", "candidates": {}}) == ("passed", ["기업 규모"])


@pytest.mark.parametrize(("info", "expected"), [
    ({"size": "중소기업", "listed": True}, ("passed", [])),
    ({"size": "중견기업", "listed": False}, ("passed", [])),
    ({"size": "스타트업", "listed": False}, ("rejected", ["기업 규모: 스타트업"])),
    ({"size": None, "listed": True}, ("passed", [])),
    ({"size": None, "listed": False}, ("passed", ["기업 규모"])),
])
def test_company_size(info, expected):
    assert check(posting(), info=info) == expected


def test_company_lookup_skipped_for_rejected_postings():
    looked_up = []
    filters.apply([posting(employment_type="계약직")], PREFS,
                  lambda name: looked_up.append(name) or BIG)
    assert looked_up == []


def test_empty_conditions_are_ignored():
    assert check(posting(location="부산", employment_type=None), info=None,
                 prefs={"hard": {}}) == ("passed", [])


def test_load_preferences_from_template():
    root = Path(__file__).parents[1]
    prefs = filters.load_preferences(root / "examples" / "data-template" / "preferences.yaml")
    assert prefs["hard"]["min_salary_10k_krw"] == 5000


def test_contract_convertible_to_permanent_is_not_permanent():
    assert check(posting(employment_type="계약직 (정규직 전환가능)"))[0] == "rejected"


def test_multiple_employment_types_pass_when_one_matches():
    assert check(posting(employment_type="정규직,계약직")) == ("passed", [])


def test_nationwide_location_passes_region_filter():
    assert check(posting(location="전국")) == ("passed", [])
