import json
from datetime import date
from pathlib import Path

import httpx

from career_ai import search
from career_ai.collectors import parse_salary, saramin, work24

FIXTURES = Path(__file__).parent / "fixtures"
SARAMIN = json.loads((FIXTURES / "saramin" / "job-search.json").read_text(encoding="utf-8"))
WORK24 = (FIXTURES / "work24" / "wanted.xml").read_bytes()


def test_saramin_posting_fields():
    first, remote, sales = saramin.parse(SARAMIN)
    assert first.model_dump() == {
        "posting_id": "saramin-49001234",
        "platform": "사람인",
        "company": "(주)한빛데이터",
        "title": "LLM 엔지니어 (경력 3년 이상)",
        "url": "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=49001234",
        "location": "서울 > 강남구,경기 > 성남시 분당구",
        "remote": False,
        "employment_type": "정규직",
        "experience": "경력 3년 이상",
        "industry": "솔루션·SI·ERP·CRM",
        "keywords": "LLM,RAG,MLOps",
        "salary": "5,000~6,000만원",
        "salary_min_10k_krw": 5000,
        "salary_max_10k_krw": 6000,
        "posted": "2026-10-13",
        "deadline": "2026-10-31",
    }
    assert remote.remote is True
    assert remote.deadline is None
    assert (remote.salary_min_10k_krw, remote.salary_max_10k_krw) == (None, None)
    assert (sales.salary_min_10k_krw, sales.salary_max_10k_krw) == (3000, None)


def test_work24_posting_fields():
    first, monthly = work24.parse(WORK24)
    assert first.posting_id == "work24-K151612610130001"
    assert first.platform == "고용24"
    assert first.location == "서울 강남구"
    assert first.employment_type == "정규직"
    assert (first.salary_min_10k_krw, first.salary_max_10k_krw) == (5000, 6000)
    assert first.posted == "2026-10-10"
    assert first.deadline == "2026-11-30"
    # 월급은 연봉으로 환산하지 않는다(상여 등을 알 수 없다).
    assert (monthly.salary_min_10k_krw, monthly.salary_max_10k_krw) == (None, None)
    assert monthly.employment_type == "계약직"
    assert monthly.deadline == "2026-12-31"


def test_parse_salary():
    assert parse_salary("5,000~6,000만원") == (5000, 6000)
    assert parse_salary("연봉 5000만원 ~ 6000만원") == (5000, 6000)
    assert parse_salary("3,000만원 이상") == (3000, None)
    assert parse_salary("4000만원") == (4000, 4000)
    assert parse_salary("회사내규에 따름") == (None, None)


def test_dedup_keeps_first_source():
    postings = saramin.parse(SARAMIN) + work24.parse(WORK24)
    ids = [p.posting_id for p in search.dedup(postings)]
    assert ids == ["saramin-49001234", "saramin-49005678", "saramin-49009999",
                   "work24-K151612610130002"]


def routes(request: httpx.Request) -> httpx.Response:
    if request.url.host == "oapi.saramin.co.kr":
        return httpx.Response(200, json=SARAMIN)
    return httpx.Response(200, content=WORK24)


def test_search_skips_sources_without_key():
    with httpx.Client(transport=httpx.MockTransport(routes)) as client:
        result = search.search(client, ["LLM"], {"SARAMIN_API_KEY": "S"}, backoff=0)
    assert {p["platform"] for p in result["postings"]} == {"사람인"}
    assert result["skipped"] == [{"source": "고용24", "reason": "WORK24_API_KEY 없음"}]


def test_search_reports_failed_source_and_keeps_others():
    def handler(request):
        if request.url.host == "oapi.saramin.co.kr":
            return httpx.Response(401, json={"code": 2, "message": "invalid access-key"})
        return routes(request)

    keys = {"SARAMIN_API_KEY": "S", "WORK24_API_KEY": "W"}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = search.search(client, ["LLM"], keys, backoff=0)
    assert len(result["postings"]) == 2
    [skipped] = result["skipped"]
    assert skipped["source"] == "사람인" and "401" in skipped["reason"]


def test_search_since_filters_and_sends_params():
    seen = []

    def handler(request):
        seen.append(request)
        return routes(request)

    keys = {"SARAMIN_API_KEY": "S", "WORK24_API_KEY": "W"}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = search.search(client, ["LLM", "RAG"], keys, since_days=2,
                               today=date(2026, 10, 13), backoff=0)
    # 고용24 첫 공고(10-10 등록)는 기간 밖, 둘째(10-11)는 안
    ids = [p["posting_id"] for p in result["postings"]]
    assert "work24-K151612610130001" not in ids
    assert "work24-K151612610130002" in ids
    sar = next(r for r in seen if r.url.host == "oapi.saramin.co.kr")
    assert sar.url.params["keywords"] == "LLM RAG"
    assert sar.url.params["access-key"] == "S"
    assert "published_min" in sar.url.params
    w24 = next(r for r in seen if r.url.host != "oapi.saramin.co.kr")
    assert w24.url.params["keyword"] == "LLM RAG"
    assert w24.url.params["authKey"] == "W"


def test_save_inbox_merges_same_day(tmp_path):
    p1, p2, _ = saramin.parse(SARAMIN)
    path = search.save_inbox(tmp_path, [p1.model_dump()], date(2026, 10, 13))
    search.save_inbox(tmp_path, [p1.model_dump(), p2.model_dump()], date(2026, 10, 13))
    assert path == tmp_path / "applications" / "_inbox" / "2026-10-13.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert [p["posting_id"] for p in saved["postings"]] == ["saramin-49001234",
                                                           "saramin-49005678"]


def test_unexpected_source_error_is_skipped_not_raised(monkeypatch):
    def boom(*args, **kwargs):
        raise KeyError("expiration-timestamp")

    monkeypatch.setattr(saramin, "search", boom)
    keys = {"SARAMIN_API_KEY": "S", "WORK24_API_KEY": "W"}
    with httpx.Client(transport=httpx.MockTransport(routes)) as client:
        result = search.search(client, ["LLM"], keys, backoff=0)
    assert [s["source"] for s in result["skipped"]] == ["사람인"]
    assert {p["platform"] for p in result["postings"]} == {"고용24"}


def test_work24_bad_item_is_skipped_not_whole_source():
    xml = WORK24.replace(b"<company>", b"<company>  ", 1)
    broken = xml.replace(b"</wanted>", b"</wanted><wanted><company></company></wanted>", 1)
    assert len(work24.parse(broken)) == len(work24.parse(WORK24))
