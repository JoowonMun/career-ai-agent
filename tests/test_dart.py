import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from career_ai.enrich import dart

FIXTURES = Path(__file__).parent / "fixtures" / "dart"


def zipped(name: str, data: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, data)
    return buf.getvalue()


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class FakeDart:
    """경로별로 저장해 둔 DART 응답을 돌려준다. 호출 기록은 calls에 남는다."""

    def __init__(self, overrides: dict[str, httpx.Response] | None = None):
        self.calls: list[httpx.Request] = []
        self.overrides = overrides or {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        name = request.url.path.rsplit("/", 1)[-1]
        if name in self.overrides:
            return self.overrides[name]
        if name == "corpCode.xml":
            return httpx.Response(200, content=zipped("CORPCODE.xml", fixture("CORPCODE.xml")))
        if name == "document.xml":
            rcept_no = request.url.params["rcept_no"]
            return httpx.Response(200, content=zipped(f"{rcept_no}.xml", fixture("document.xml")))
        files = {"company.json": "company.json", "list.json": "list.json",
                 "fnlttSinglAcnt.json": "fnltt.json"}
        return httpx.Response(200, content=fixture(files[name]))


def client_for(fake: FakeDart) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(fake))


@pytest.fixture
def corps():
    return dart.parse_corp_codes(fixture("CORPCODE.xml"))


def test_parse_corp_codes_blank_stock_code_is_none(corps):
    by_code = {c["corp_code"]: c for c in corps}
    assert by_code["00126380"]["stock_code"] == "005930"
    assert by_code["00258999"]["stock_code"] is None


def test_exact_name_wins_over_partial(corps):
    assert [c["corp_code"] for c in dart.find_corp(corps, "삼성전자")] == ["00126380"]


def test_name_is_normalized(corps):
    assert [c["corp_code"] for c in dart.find_corp(corps, "(주) 삼성 전자")] == ["00126380"]
    assert [c["corp_code"] for c in dart.find_corp(corps, "삼성전자 주식회사")] == ["00126380"]


def test_same_name_returns_all_listed_first(corps):
    assert [c["corp_code"] for c in dart.find_corp(corps, "한빛데이터")] == [
        "02222222",
        "01111111",
    ]


def test_partial_match_when_no_exact(corps):
    assert [c["corp_name"] for c in dart.find_corp(corps, "전자서비스")] == ["삼성전자서비스"]


def test_corp_code_cache_is_reused(tmp_path):
    fake = FakeDart()
    cache = tmp_path / "corpcode.xml"
    with client_for(fake) as client:
        dart.load_corp_codes(client, "KEY", cache, backoff=0)
        dart.load_corp_codes(client, "KEY", cache, backoff=0)
    assert len(fake.calls) == 1
    assert cache.exists()


def test_corp_code_error_response_raises(tmp_path):
    error = "<result><status>010</status><message>등록되지 않은 키입니다.</message></result>"
    fake = FakeDart({"corpCode.xml": httpx.Response(200, content=error.encode())})
    with client_for(fake) as client, pytest.raises(dart.DartError, match="등록되지 않은 키"):
        dart.load_corp_codes(client, "KEY", tmp_path / "c.xml", backoff=0)
    assert not (tmp_path / "c.xml").exists()


def test_parse_business_splits_revenue_mix():
    result = dart.parse_business(fixture("document.xml").decode("utf-8"))
    assert [s["title"] for s in result["business"]] == [
        "1. 사업의 개요",
        "6. 주요계약 및 연구개발활동",
    ]
    assert "R&D 투자를 <확대>하고" in result["business"][0]["text"]
    assert "재무 본문" not in json.dumps(result, ensure_ascii=False)
    [mix] = result["revenue_mix"]
    assert mix["title"] == "2. 주요 제품 및 서비스"
    assert "DX 부문 | 174조 | 58%" in mix["text"]


def test_parse_business_truncates_long_section():
    body = "가" * (dart.SECTION_MAX_CHARS + 10)
    xml = (
        "<SECTION-1><TITLE>II. 사업의 내용</TITLE>"
        f"<SECTION-2><TITLE>1. 사업의 개요</TITLE><P>{body}</P></SECTION-2></SECTION-1>"
    )
    [section] = dart.parse_business(xml)["business"]
    assert len(section["text"]) == dart.SECTION_MAX_CHARS
    assert section["truncated"] is True


def test_parse_financials_prefers_consolidated():
    items = json.loads(fixture("fnltt.json"))["list"]
    result = dart.parse_financials(items)
    assert result["statement"] == "연결재무제표"
    assert result["unit"] == "KRW"
    assert result["accounts"][0] == {
        "account": "매출액",
        "2025": 300870903000000,
        "2024": 300870903000000,
        "2023": 258935494000000,
    }
    net = result["accounts"][2]
    assert net["2025"] == -1000000
    assert net["2023"] is None


def test_lookup_returns_report_with_latest_business_report(tmp_path):
    fake = FakeDart()
    with client_for(fake) as client:
        result = dart.lookup(client, "KEY", tmp_path / "c.xml", name="삼성전자", backoff=0)
    assert result["corp_code"] == "00126380"
    assert result["overview"]["corp_name"] == "삼성전자(주)"
    assert result["report"] == {
        "name": "[기재정정]사업보고서 (2025.12)",
        "rcept_no": "20260320000123",
        "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260320000123",
    }
    assert result["business"][0]["title"] == "1. 사업의 개요"
    assert result["financials"]["accounts"][0]["account"] == "매출액"
    fnltt = next(r for r in fake.calls if r.url.path.endswith("fnlttSinglAcnt.json"))
    assert fnltt.url.params["bsns_year"] == "2025"
    assert fnltt.url.params["reprt_code"] == "11011"


def test_lookup_returns_candidates_when_ambiguous(tmp_path):
    with client_for(FakeDart()) as client:
        result = dart.lookup(client, "KEY", tmp_path / "c.xml", name="한빛데이터", backoff=0)
    assert [c["corp_code"] for c in result["candidates"]] == ["02222222", "01111111"]


def test_lookup_returns_empty_candidates_when_not_found(tmp_path):
    with client_for(FakeDart()) as client:
        result = dart.lookup(client, "KEY", tmp_path / "c.xml", name="없는회사", backoff=0)
    assert result == {"candidates": []}


def test_lookup_by_corp_code_skips_corp_list(tmp_path):
    fake = FakeDart()
    with client_for(fake) as client:
        result = dart.lookup(client, "KEY", tmp_path / "c.xml", corp_code="00126380", backoff=0)
    assert result["corp_code"] == "00126380"
    assert not any(r.url.path.endswith("corpCode.xml") for r in fake.calls)


def test_lookup_without_business_report(tmp_path):
    no_data = httpx.Response(200, json={"status": "013", "message": "조회된 데이타가 없습니다."})
    fake = FakeDart({"list.json": no_data})
    with client_for(fake) as client:
        result = dart.lookup(client, "KEY", tmp_path / "c.xml", corp_code="00126380", backoff=0)
    assert result["report"] is None
    assert result["business"] == []
    assert result["financials"] is None


def test_corp_code_list_is_parsed_once_per_process(tmp_path, monkeypatch):
    cache = tmp_path / "corp.xml"
    cache.write_bytes(fixture("CORPCODE.xml"))
    dart._CORP_MEMO.clear()
    calls = []
    original = dart.parse_corp_codes

    def counting(data):
        calls.append(1)
        return original(data)

    monkeypatch.setattr(dart, "parse_corp_codes", counting)
    with httpx.Client(transport=httpx.MockTransport(FakeDart())) as client:
        dart.load_corp_codes(client, "K", cache)
        dart.load_corp_codes(client, "K", cache)
    assert calls == [1]


def test_english_abbreviation_matches_korean_registered_name():
    corps = [
        {"corp_code": "1", "corp_name": "에스케이브로드밴드", "stock_code": None},
        {"corp_code": "2", "corp_name": "엘지씨엔에스", "stock_code": "064400"},
    ]
    assert [c["corp_code"] for c in dart.find_corp(corps, "SK브로드밴드")] == ["1"]
    assert dart.pick_corp(dart.find_corp(corps, "SK브로드밴드"), "SK브로드밴드")["corp_code"] == "1"
    assert [c["corp_code"] for c in dart.find_corp(corps, "LG CNS")] == ["2"]
