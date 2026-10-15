import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from career_ai.charcount import check_application, write_final
from career_ai.cli import main


def make_app(tmp_path: Path) -> Path:
    app = tmp_path / "샘플전자_S001"
    (app / "drafts").mkdir(parents=True)
    questions = {
        "questions": [
            {"id": 1, "text": "지원 동기를 쓰세요.", "limit": 10,
             "count_mode": "with_spaces", "source": "paste"},
            {"id": 2, "text": "협업 경험을 쓰세요.", "limit": 10,
             "count_mode": "without_spaces", "source": "paste"},
        ]
    }
    (app / "questions.json").write_text(json.dumps(questions, ensure_ascii=False), encoding="utf-8")
    (app / "drafts" / "q1_final.md").write_text(
        "가나다라마바사 👍 <!-- src: projects/a.md -->\r\n", encoding="utf-8", newline=""
    )
    return app


def test_check_reports_ok_and_missing(tmp_path):
    results = check_application(make_app(tmp_path))
    assert [(r["id"], r["length"], r["status"]) for r in results] == [
        (1, 9, "ok"),
        (2, None, "missing"),
    ]


def test_write_final_refuses_when_missing(tmp_path):
    app = make_app(tmp_path)
    with pytest.raises(ValueError, match="Q2"):
        write_final(app, check_application(app))
    assert not (app / "final.md").exists()


def test_unclosed_comment_is_reported_and_blocks_final(tmp_path):
    app = make_app(tmp_path)
    (app / "drafts" / "q2_final.md").write_text("함께 일했다 <!-- src: a.md", encoding="utf-8")
    results = check_application(app)
    assert results[1]["status"] == "comment_left"
    with pytest.raises(ValueError, match="Q2"):
        write_final(app, results)


def test_questions_json_with_bom_loads(tmp_path):
    app = make_app(tmp_path)
    path = app / "questions.json"
    path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8-sig")
    assert check_application(app)[0]["status"] == "ok"


def test_write_final_strips_comments(tmp_path):
    app = make_app(tmp_path)
    (app / "drafts" / "q2_final.md").write_text("함께 일했다", encoding="utf-8")
    path = write_final(app, check_application(app))
    text = path.read_text(encoding="utf-8")
    assert "## Q1. 지원 동기를 쓰세요." in text
    assert "(9 / 10자, 공백 포함)" in text
    assert "<!--" not in text


def test_count_command_finds_app_under_data_dir(tmp_path, monkeypatch, capsys):
    data = tmp_path / "data"
    make_app(data / "applications")
    monkeypatch.setenv("CAREER_DATA_DIR", str(data))
    monkeypatch.chdir(tmp_path)

    assert main(["count", "샘플전자_S001"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["results"][0]["status"] == "ok"
    assert out["final"] is None


def test_count_write_final_error_returns_1(tmp_path, capsys):
    app = make_app(tmp_path)
    assert main(["count", str(app), "--write-final"]) == 1
    assert "Q2" in json.loads(capsys.readouterr().out)["error"]


def test_korean_output_survives_cp949_console(tmp_path):
    app = make_app(tmp_path)
    env = {**os.environ, "PYTHONIOENCODING": "cp949"}
    result = subprocess.run(
        [sys.executable, "-m", "career_ai", "count", str(app)],
        capture_output=True, env=env,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert "샘플전자" in result.stdout.decode("utf-8")


def test_clean_command_writes_normalized_text(tmp_path, capsys):
    src = tmp_path / "q1_v1.md"
    src.write_text(
        "첫 문장. <!-- src: projects/a.md -->\r\n둘째 문장.\r\n", encoding="utf-8", newline=""
    )
    out = tmp_path / "q1_clean.md"

    assert main(["clean", str(src), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == "첫 문장.\n둘째 문장.\n"
