import json
import shutil
from pathlib import Path

import pytest

from career_ai import cli
from career_ai.enrich import company

ROOT = Path(__file__).parents[1]
KEYS = ("SARAMIN_API_KEY", "WORK24_API_KEY", "DART_API_KEY", "DATA_GO_KR_API_KEY")


@pytest.fixture
def data(tmp_path, monkeypatch):
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)
    data = tmp_path / "data"
    shutil.copytree(ROOT / "examples" / "data-template", data)
    monkeypatch.setenv("CAREER_DATA_DIR", str(data))
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    return data


def run(capsys, *args):
    code = cli.main(list(args))
    return code, json.loads(capsys.readouterr().out)


def test_search_without_keys_saves_empty_inbox_and_reports_skipped(data, capsys):
    code, out = run(capsys, "search", "LLM", "--since", "7d")
    assert code == 0
    assert out["count"] == 0
    assert [s["source"] for s in out["skipped"]] == ["사람인", "고용24"]
    assert Path(out["inbox"]).parent == data / "applications" / "_inbox"


def test_since_must_be_days(data, capsys):
    with pytest.raises(SystemExit):
        cli.main(["search", "LLM", "--since", "1w"])


def test_filter_uses_preferences_and_company_cache(data, capsys, monkeypatch):
    inbox = data / "applications" / "_inbox" / "2026-10-13.json"
    postings = [
        {"posting_id": "saramin-1", "company": "한빛데이터", "title": "LLM 엔지니어",
         "location": "서울 > 강남구", "remote": False, "employment_type": "정규직",
         "salary_min_10k_krw": None, "salary_max_10k_krw": None},
        {"posting_id": "saramin-2", "company": "한빛데이터", "title": "AI 영업",
         "location": "서울", "remote": False, "employment_type": "정규직",
         "salary_min_10k_krw": None, "salary_max_10k_krw": None},
    ]
    inbox.write_text(json.dumps({"postings": postings}, ensure_ascii=False), encoding="utf-8")
    seen = []

    def fake_lookup(client, keys, name, cache_dir, **kwargs):
        seen.append((name, cache_dir))
        return {"size": "대기업", "listed": False}

    monkeypatch.setattr(company, "lookup", fake_lookup)
    code, out = run(capsys, "filter", "2026-10-13.json")
    assert code == 0
    assert [p["posting_id"] for p in out["passed"]] == ["saramin-1"]
    assert out["passed"][0]["unknown"] == ["연봉"]
    assert out["rejected"][0]["reasons"] == ["제외 키워드: 영업"]
    assert seen == [("한빛데이터", data / "companies")]


def test_filter_missing_inbox(data, capsys):
    code, out = run(capsys, "filter", "없는파일.json")
    assert code == 2 and out["error"] == "not_found"


def test_company_prints_lookup_result(data, capsys, monkeypatch):
    monkeypatch.setattr(company, "lookup",
                        lambda client, keys, name, cache_dir, **kw: {"name": name, **kw})
    code, out = run(capsys, "company", "삼성전자", "--corp-code", "00126380")
    assert code == 0
    assert out == {"name": "삼성전자", "corp_code": "00126380", "nps_seq": None}


def test_filter_looks_up_each_company_once(data, capsys, monkeypatch):
    inbox = data / "applications" / "_inbox" / "2026-10-13.json"
    base = {"company": "한빛데이터", "title": "LLM 엔지니어", "location": "서울",
            "remote": False, "employment_type": "정규직",
            "salary_min_10k_krw": 6000, "salary_max_10k_krw": 7000}
    postings = [{**base, "posting_id": "a"}, {**base, "posting_id": "b"}]
    inbox.write_text(json.dumps({"postings": postings}, ensure_ascii=False), encoding="utf-8")
    calls = []

    def fake_lookup(client, keys, name, cache_dir, **kwargs):
        calls.append(name)
        return {"size": "대기업", "listed": True}

    monkeypatch.setattr(company, "lookup", fake_lookup)
    code, out = run(capsys, "filter", "2026-10-13.json")
    assert code == 0 and len(out["passed"]) == 2
    assert calls == ["한빛데이터"]


def test_unexpected_error_is_reported_as_json(data, capsys, monkeypatch):
    def boom(args):
        raise RuntimeError("예상 못 한 오류")

    monkeypatch.setattr(cli, "cmd_search", boom)
    code, out = run(capsys, "search", "LLM")
    assert code == 2
    assert out["error"] == "internal" and "예상 못 한 오류" in out["message"]


def test_interactive_fetch_turns_form_questions_into_questions(data, capsys, monkeypatch):
    from career_ai.collectors import page

    def fake_interactive(url):
        return {"url": "https://site.test/resume/1", "page_text": "작성 화면",
                "earlier_pages": [{"url": url, "page_text": "공고 본문"}],
                "form_questions": ["1. 지원 동기 (최대 500자)"], "questions_locked": False}

    monkeypatch.setattr(page, "interactive", fake_interactive)
    code, out = run(capsys, "fetch", "--interactive", "https://site.test/recruit/1")
    assert code == 0
    assert out["parser"] == "form"
    assert out["questions"][0]["limit"] == 500
    assert out["earlier_pages"][0]["page_text"] == "공고 본문"
