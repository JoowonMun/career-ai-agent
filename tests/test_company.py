import io
import json
import zipfile
from datetime import date
from pathlib import Path

import httpx
import pytest

from career_ai.enrich import company, dart, nps

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 10, 13)
KEYS = {"DART_API_KEY": "D", "DATA_GO_KR_API_KEY": "N"}


def fixture(path: str) -> bytes:
    return (FIXTURES / path).read_bytes()


def corp_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CORPCODE.xml", fixture("dart/CORPCODE.xml"))
    return buf.getvalue()


class Fake:
    def __init__(self, overrides: dict[str, httpx.Response] | None = None):
        self.calls: list[httpx.Request] = []
        self.overrides = overrides or {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        name = request.url.path.rsplit("/", 1)[-1]
        if name in self.overrides:
            return self.overrides[name]
        if name == "corpCode.xml":
            return httpx.Response(200, content=corp_zip())
        files = {
            "company.json": "dart/company.json",
            "empSttus.json": "dart/empSttus.json",
            "getBassInfoSearchV2": "nps/bass.xml",
            "getDetailInfoSearchV2": "nps/detail.xml",
        }
        return httpx.Response(200, content=fixture(files[name]))


def run(tmp_path, name, fake=None, keys=KEYS, **kwargs):
    fake = fake or Fake()
    with httpx.Client(transport=httpx.MockTransport(fake)) as client:
        result = company.lookup(client, keys, name, tmp_path / "companies",
                                corp_cache=tmp_path / "corp.xml", today=TODAY, backoff=0,
                                **kwargs)
    return result, fake


@pytest.mark.parametrize(("employees", "founded", "expected"), [
    (1000, None, "대기업"),
    (999, None, "중견기업"),
    (300, None, "중견기업"),
    (299, None, "중소기업"),
    (299, date(2019, 10, 13), "스타트업"),
    (299, date(2019, 10, 12), "중소기업"),
    (1500, date(2024, 1, 1), "대기업"),
    (None, date(2024, 1, 1), None),
])
def test_classify(employees, founded, expected):
    assert company.classify(employees, founded, TODAY) == expected


def test_parse_employees_sums_rows():
    data = json.loads(fixture("dart/empSttus.json"))
    # 급여 총액 3.4조 원 / 30,000명 = 1억 1,333만 원
    assert dart.parse_employees(data["list"]) == (30000, 11333)


def test_parse_employees_uses_total_rows_only():
    data = json.loads(fixture("dart/empSttus-total.json"))
    assert dart.parse_employees(data["list"]) == (1000, 7400)


def test_listed_company_from_dart_and_cached(tmp_path):
    result, fake = run(tmp_path, "삼성전자")
    assert result == {
        "name": "삼성전자",
        "listed": True,
        "size": "대기업",
        "employees": 30000,
        "avg_salary_10k_krw": 11333,
        "founded": "1969-01-13",
        "sources": ["DART 2025 사업보고서"],
        "errors": [],
        "fetched": "2026-10-13",
    }
    emp = next(r for r in fake.calls if r.url.path.endswith("empSttus.json"))
    assert emp.url.params["bsns_year"] == "2025"
    assert not any("data.go.kr" in str(r.url) for r in fake.calls)

    again, fake2 = run(tmp_path, "삼성전자")
    assert again == {**result, "cached": True}
    assert fake2.calls == []


def test_cache_expires_after_90_days(tmp_path):
    run(tmp_path, "삼성전자")
    path = next((tmp_path / "companies").glob("*.json"))
    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**data, "fetched": "2026-07-14"}), encoding="utf-8")
    result, fake = run(tmp_path, "삼성전자")
    assert "cached" not in result and fake.calls


def test_falls_back_to_previous_year(tmp_path):
    no_data = {"status": "013", "message": "조회된 데이타가 없습니다."}
    calls = []

    class Older(Fake):
        def __call__(self, request):
            if request.url.path.endswith("empSttus.json"):
                calls.append(request.url.params["bsns_year"])
                if request.url.params["bsns_year"] == "2025":
                    return httpx.Response(200, json=no_data)
            return super().__call__(request)

    result, _ = run(tmp_path, "삼성전자", Older())
    assert calls == ["2025", "2024"]
    assert result["sources"] == ["DART 2024 사업보고서"]


def test_unlisted_company_uses_nps(tmp_path):
    result, fake = run(tmp_path, "작은회사")
    # DART에 없다고 비상장으로 단정하지 않는다(등록명이 다를 수 있다).
    assert result["listed"] is None
    assert result["employees"] == 42
    assert result["founded"] == "2022-03-01"
    assert result["size"] == "스타트업"
    assert result["avg_salary_10k_krw"] is None
    assert result["sources"] == ["국민연금 가입 사업장 2026-09"]
    detail = next(r for r in fake.calls if r.url.path.endswith("getDetailInfoSearchV2"))
    assert detail.url.params["seq"] == "11111"


def test_nps_matches_exclude_closed_and_other_names():
    workplaces = nps.parse_workplaces(fixture("nps/bass.xml"))
    assert [w["seq"] for w in nps.find(workplaces, "작은회사")] == ["11111"]


def test_ambiguous_dart_returns_candidates_and_is_not_cached(tmp_path):
    result, _ = run(tmp_path, "한빛데이터")
    assert result["candidates"]["source"] == "DART"
    assert [c["corp_code"] for c in result["candidates"]["items"]] == ["02222222", "01111111"]
    assert not (tmp_path / "companies").exists()


def test_corp_code_resolves_ambiguity(tmp_path):
    result, _ = run(tmp_path, "한빛데이터", corp_code="02222222")
    assert result["listed"] is True


def test_no_keys_leaves_everything_unknown(tmp_path):
    result, fake = run(tmp_path, "삼성전자", keys={})
    assert result["size"] is None and result["listed"] is None
    assert result["errors"] == ["DART_API_KEY 없음", "DATA_GO_KR_API_KEY 없음"]
    assert fake.calls == []
    assert not (tmp_path / "companies").exists()


def test_nps_error_is_recorded(tmp_path):
    error = httpx.Response(200, content=fixture("nps/error.xml"))
    result, _ = run(tmp_path, "작은회사", Fake({"getBassInfoSearchV2": error}))
    assert result["size"] is None
    assert any("SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in e for e in result["errors"])


def test_parse_employees_prefers_grand_total_over_division_totals():
    rows = [
        {"fo_bbm": "반도체", "sexdstn": "남", "sm": "600", "fyer_salary_totamt": "60,000,000,000"},
        {"fo_bbm": "반도체", "sexdstn": "여", "sm": "400", "fyer_salary_totamt": "40,000,000,000"},
        {"fo_bbm": "반도체", "sexdstn": "합계", "sm": "1,000", 
         "fyer_salary_totamt": "100,000,000,000"},
        {"fo_bbm": "가전", "sexdstn": "남", "sm": "300", "fyer_salary_totamt": "30,000,000,000"},
        {"fo_bbm": "가전", "sexdstn": "소계", "sm": "300", "fyer_salary_totamt": "30,000,000,000"},
        {"fo_bbm": "합계", "sexdstn": "합계", "sm": "1,300", 
         "fyer_salary_totamt": "130,000,000,000"},
    ]
    assert dart.parse_employees(rows) == (1300, 10000)


def test_parse_employees_sums_only_gender_rows_without_grand_total():
    rows = [
        {"fo_bbm": "반도체", "sexdstn": "남", "sm": "600", "fyer_salary_totamt": None},
        {"fo_bbm": "반도체", "sexdstn": "소계", "sm": "600", "fyer_salary_totamt": None},
        {"fo_bbm": None, "sexdstn": "여", "sm": "400", "fyer_salary_totamt": None},
    ]
    assert dart.parse_employees(rows) == (1000, None)


def test_single_partial_dart_match_is_a_candidate_not_a_pick(tmp_path):
    result, _ = run(tmp_path, "전자서비스")
    assert result["candidates"]["source"] == "DART"


def test_name_missing_from_dart_is_not_marked_unlisted(tmp_path):
    result, _ = run(tmp_path, "없는회사이름", keys={"DART_API_KEY": "D"})
    assert result["listed"] is None


def test_unexpected_error_in_a_step_is_recorded(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise ValueError("이상한 응답")

    monkeypatch.setattr(company.dart, "overview", boom)
    result, _ = run(tmp_path, "삼성전자")
    assert any("이상한 응답" in e for e in result["errors"])


def test_parse_employees_uses_gender_rows_under_total_division():
    # 삼성전자 2025 사업보고서 형태: 전체 합계가 '성별합계' 부문의 남·여 두 줄로 온다.
    rows = [
        {"fo_bbm": "DX", "sexdstn": "남", "sm": "40,000", "fyer_salary_totamt": "-"},
        {"fo_bbm": "DX", "sexdstn": "여", "sm": "20,000", "fyer_salary_totamt": "-"},
        {"fo_bbm": "DS", "sexdstn": "남", "sm": "54,273", "fyer_salary_totamt": "-"},
        {"fo_bbm": "DS", "sexdstn": "여", "sm": "14,608", "fyer_salary_totamt": "-"},
        {"fo_bbm": "성별합계", "sexdstn": "남", "sm": "94,273",
         "fyer_salary_totamt": "15,562,454,000,000"},
        {"fo_bbm": "성별합계", "sexdstn": "여", "sm": "34,608",
         "fyer_salary_totamt": "4,237,308,000,000"},
    ]
    assert dart.parse_employees(rows) == (128881, 15363)
