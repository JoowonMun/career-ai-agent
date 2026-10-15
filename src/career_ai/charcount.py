"""자소서 글자수 계산. 세는 방식은 문항마다 다르므로 questions.json의 설정을 따른다."""

import re
import unicodedata
from pathlib import Path
from typing import Literal

import regex

from career_ai.models import CountMode, QuestionSet

UNDER_RATIO = 0.8

_SOURCE_COMMENT = re.compile(r"[ \t]*<!--.*?-->", re.DOTALL)
_NEWLINE = re.compile(r"\r\n|\r|\n")
_WHITESPACE = re.compile(r"\s")
_GRAPHEME = regex.compile(r"\X")


_HUMANIZE_SUMMARY = "<!-- HUMANIZE-SUMMARY"


def normalize(text: str) -> str:
    """NFC 정규화, BOM·교정 요약·근거 주석 제거, 줄바꿈 통일, 앞뒤 공백 제거."""
    text = unicodedata.normalize("NFC", text).replace("﻿", "")
    # humanize-korean 결과 끝에 붙는 요약 블록은 본문이 아니다.
    text = text.split(_HUMANIZE_SUMMARY, 1)[0]
    text = _SOURCE_COMMENT.sub("", text)
    text = _NEWLINE.sub("\n", text)
    return text.strip()


def _graphemes(text: str) -> int:
    return len(_GRAPHEME.findall(text))


def count(
    text: str,
    mode: CountMode,
    *,
    count_newlines: bool = False,
    hangul_bytes: int = 2,
) -> int:
    text = normalize(text)
    if mode == "without_spaces":
        return _graphemes(_WHITESPACE.sub("", text))
    if not count_newlines:
        text = text.replace("\n", "")
    if mode == "with_spaces":
        return _graphemes(text)
    if mode == "bytes":
        if hangul_bytes == 3:
            return len(text.encode("utf-8"))
        return sum(1 if ord(ch) < 128 else 2 for ch in text)
    raise ValueError(f"알 수 없는 세는 방식: {mode}")


def judge(length: int, limit: int | None) -> Literal["ok", "over", "under", "no_limit"]:
    if limit is None:
        return "no_limit"
    if length > limit:
        return "over"
    if length < limit * UNDER_RATIO:
        return "under"
    return "ok"


MODE_LABELS = {"with_spaces": "공백 포함", "without_spaces": "공백 제외", "bytes": "바이트"}


def _draft_path(app_dir: Path, question_id: int) -> Path:
    return app_dir / "drafts" / f"q{question_id}_final.md"


def check_application(app_dir: Path) -> list[dict]:
    question_set = QuestionSet.load(app_dir / "questions.json")
    results = []
    for q in question_set.questions:
        path = _draft_path(app_dir, q.id)
        result = {"id": q.id, "file": str(path), "limit": q.limit, "mode": q.count_mode}
        if not path.exists():
            results.append({**result, "length": None, "status": "missing"})
            continue
        text = path.read_text(encoding="utf-8")
        length = count(
            text,
            q.count_mode,
            count_newlines=q.count_newlines,
            hangul_bytes=q.hangul_bytes,
        )
        cleaned = normalize(text)
        # 닫히지 않은 주석 등이 남으면 글자수도 최종본도 믿을 수 없다.
        status = "comment_left" if "<!--" in cleaned or "-->" in cleaned else judge(length, q.limit)
        results.append({**result, "length": length, "status": status})
    return results


BLOCKING_STATUSES = ("over", "missing", "comment_left")


def write_final(app_dir: Path, results: list[dict]) -> Path:
    blocked = [f"Q{r['id']}({r['status']})" for r in results if r["status"] in BLOCKING_STATUSES]
    if blocked:
        raise ValueError(f"final.md를 만들 수 없습니다: {', '.join(blocked)}")
    question_set = QuestionSet.load(app_dir / "questions.json")
    by_id = {r["id"]: r for r in results}
    parts = ["# 자기소개서 최종본"]
    for q in question_set.questions:
        r = by_id[q.id]
        label = MODE_LABELS[q.count_mode]
        size = f"{r['length']} / {q.limit}자" if q.limit else f"{r['length']}자"
        body = normalize(_draft_path(app_dir, q.id).read_text(encoding="utf-8"))
        parts.append(f"## Q{q.id}. {q.text}\n({size}, {label})\n\n{body}")
    path = app_dir / "final.md"
    path.write_text("\n\n".join(parts) + "\n", encoding="utf-8", newline="\n")
    return path
