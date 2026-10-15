import unicodedata

import pytest
from pydantic import ValidationError

from career_ai.charcount import count, judge, normalize
from career_ai.models import Question


class TestWithSpaces:
    def test_counts_spaces_but_not_newlines_by_default(self):
        assert count("가나 다\n라", "with_spaces") == 5

    def test_counts_newlines_when_enabled(self):
        assert count("가나 다\n라", "with_spaces", count_newlines=True) == 6

    def test_crlf_is_one_newline(self):
        assert count("가\r\n나", "with_spaces", count_newlines=True) == 3

    def test_emoji_sequence_is_one_character(self):
        assert count("👨‍👩‍👧 가", "with_spaces") == 3

    def test_nfd_hangul_counts_same_as_nfc(self):
        assert count(unicodedata.normalize("NFD", "한글"), "with_spaces") == 2

    def test_strips_leading_and_trailing_whitespace(self):
        assert count("  가나  \n", "with_spaces") == 2


class TestWithoutSpaces:
    def test_removes_all_unicode_whitespace(self):
        assert count("가 나\t다\n라 마", "without_spaces") == 5


class TestBytes:
    def test_euc_kr_style_hangul_two_bytes(self):
        assert count("AI 엔지니어", "bytes") == 11

    def test_utf8_style_hangul_three_bytes(self):
        assert count("AI 엔지니어", "bytes", hangul_bytes=3) == 15

    def test_nfd_input_normalized_before_bytes(self):
        assert count(unicodedata.normalize("NFD", "한글"), "bytes", hangul_bytes=3) == 6

    def test_crlf_counts_one_byte_when_enabled(self):
        assert count("가\r\n나", "bytes", count_newlines=True) == 5


class TestSourceComments:
    def test_comments_are_not_counted(self):
        text = "문장입니다. <!-- src: projects/a.md -->\n다음 문장."
        assert count(text, "with_spaces") == 12

    def test_normalize_removes_comments(self):
        assert "<!--" not in normalize("가 <!-- src: x.md -->\n나")

    def test_inline_comment_between_sentences_keeps_one_space(self):
        text = "첫 문장. <!-- src: a.md --> 둘째 문장. <!-- src: b.md -->\n\n새 문단."
        assert normalize(text) == "첫 문장. 둘째 문장.\n\n새 문단."


class TestLeftovers:
    def test_bom_is_not_counted(self):
        assert count("﻿가나다", "with_spaces") == 3

    def test_humanize_summary_block_is_dropped(self):
        text = "본문입니다.\n\n<!-- HUMANIZE-SUMMARY -->\n- 변경률: 12%\n- 등급: A\n"
        assert normalize(text) == "본문입니다."


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        count("가", "chars")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("length", "limit", "expected"),
    [
        (500, 500, "ok"),
        (501, 500, "over"),
        (400, 500, "ok"),
        (399, 500, "under"),
        (10, None, "no_limit"),
    ],
)
def test_judge(length, limit, expected):
    assert judge(length, limit) == expected


def test_question_requires_count_mode():
    with pytest.raises(ValidationError):
        Question(id=1, text="지원 동기", limit=500, source="paste")
