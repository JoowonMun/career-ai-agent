import json

import pytest

from career_ai.cli import main, page_id_from


@pytest.fixture(autouse=True)
def no_notion_env(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "")
    monkeypatch.setenv("NOTION_DATA_SOURCE_ID", "")


def test_page_id_from_url():
    url = "https://www.notion.so/myspace/abc-1234567890abcdef1234567890abcdef?pvs=4"
    assert page_id_from(url) == "1234567890abcdef1234567890abcdef"
    dashed = "12345678-90ab-cdef-1234-567890abcdef"
    assert page_id_from(dashed) == "1234567890abcdef1234567890abcdef"


def test_page_id_from_rejects_garbage():
    with pytest.raises(ValueError):
        page_id_from("https://www.notion.so/no-id-here")


def test_push_without_token_reports_config_error(tmp_path, capsys):
    assert main(["notion", "push", str(tmp_path)]) == 2
    out = json.loads(capsys.readouterr().out)
    assert out["error"] == "config"
    assert "NOTION_TOKEN" in out["message"]
