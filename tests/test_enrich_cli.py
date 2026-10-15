import json

import pytest

from career_ai import cli
from career_ai.enrich import dart, news

KEYS = ("DART_API_KEY", "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET")


@pytest.fixture(autouse=True)
def no_keys(monkeypatch, tmp_path):
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)
    # 저장소의 실제 .env를 읽지 않도록 빈 저장소 루트를 쓴다.
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)


def run(capsys, *args):
    code = cli.main(list(args))
    return code, json.loads(capsys.readouterr().out)


def test_dart_without_key_reports_missing_key(capsys):
    code, out = run(capsys, "dart", "삼성전자")
    assert code == 2
    assert out["error"] == "missing_key"
    assert "DART_API_KEY" in out["message"]


def test_news_without_naver_key_uses_google_news(capsys, monkeypatch):
    calls = []

    def fake_google(client, query, *, months):
        calls.append((query, months))
        return [{"title": "기사", "url": "u", "date": "2026-10-14", "summary": "",
                 "source": "세계일보"}]

    monkeypatch.setattr(news, "search_google_news", fake_google)
    code, out = run(capsys, "news", "삼성전자")
    assert code == 0
    assert calls == [("삼성전자", 6)]
    assert out[0]["source"] == "세계일보"


def test_dart_passes_corp_code_and_prints_result(capsys, monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "KEY")
    seen = {}

    def fake_lookup(client, key, **kwargs):
        seen.update(kwargs, key=key)
        return {"candidates": []}

    monkeypatch.setattr(dart, "lookup", fake_lookup)
    code, out = run(capsys, "dart", "삼성전자", "--corp-code", "00126380")
    assert code == 0
    assert out == {"candidates": []}
    assert seen == {"key": "KEY", "name": "삼성전자", "corp_code": "00126380"}


def test_dart_error_is_reported(capsys, monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "KEY")

    def broken(client, key, **kwargs):
        raise dart.DartError("020: 요청 제한을 초과하였습니다.")

    monkeypatch.setattr(dart, "lookup", broken)
    code, out = run(capsys, "dart", "삼성전자")
    assert code == 2
    assert out == {"error": "dart", "message": "020: 요청 제한을 초과하였습니다."}
