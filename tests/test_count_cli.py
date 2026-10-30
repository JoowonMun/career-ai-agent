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


def test_check_accepts_free_questions(tmp_path):
    # 공고에 문항이 없어 preferences의 자유 문항으로 만든 questions.json
    app = make_app(tmp_path)
    data = json.loads((app / "questions.json").read_text(encoding="utf-8"))
    for q in data["questions"]:
        q["source"] = "free"
    (app / "questions.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert check_application(app)[0]["status"] == "ok"


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


def test_count_single_file_uses_question_settings(tmp_path, capsys):
    app = make_app(tmp_path)
    review = app / "drafts" / "q2_review.md"
    review.write_text("함께 일했다", encoding="utf-8")

    assert main(["count", str(app), "--question", "2", "--file", str(review)]) == 0
    results = json.loads(capsys.readouterr().out)["results"]
    assert [(r["id"], r["length"], r["status"], r["file"]) for r in results] == [
        (2, 5, "ok", str(review)),
    ]


def test_count_file_without_question_fails(tmp_path, capsys):
    app = make_app(tmp_path)
    assert main(["count", str(app), "--file", str(app / "drafts" / "q1_final.md")]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "usage"


def make_long_app(tmp_path: Path, limit: int | None) -> Path:
    app = tmp_path / "long"
    (app / "drafts").mkdir(parents=True)
    questions = {"questions": [{"id": 1, "text": "경험을 쓰세요.", "limit": limit,
                                "count_mode": "with_spaces", "source": "paste"}]}
    (app / "questions.json").write_text(json.dumps(questions, ensure_ascii=False), encoding="utf-8")
    return app


def test_long_question_without_title_blocks_final(tmp_path):
    app = make_long_app(tmp_path, 600)
    (app / "drafts" / "q1_final.md").write_text("가" * 590, encoding="utf-8")
    results = check_application(app)
    assert results[0]["status"] == "no_title"
    with pytest.raises(ValueError, match="Q1"):
        write_final(app, results)


def test_long_question_with_title_passes(tmp_path):
    app = make_long_app(tmp_path, 600)
    (app / "drafts" / "q1_final.md").write_text("[핵심 내용]\n\n" + "가" * 580, encoding="utf-8")
    assert check_application(app)[0]["status"] == "ok"


def test_unlimited_question_needs_title(tmp_path):
    app = make_long_app(tmp_path, None)
    (app / "drafts" / "q1_final.md").write_text("본문만 있습니다.", encoding="utf-8")
    assert check_application(app)[0]["status"] == "no_title"


def test_over_limit_is_reported_before_missing_title(tmp_path):
    app = make_long_app(tmp_path, 600)
    (app / "drafts" / "q1_final.md").write_text("가" * 700, encoding="utf-8")
    assert check_application(app)[0]["status"] == "over"
