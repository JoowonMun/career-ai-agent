from career_ai.notion_blocks import MAX_TEXT, markdown_to_blocks, plain_text, rich_text


def types(blocks):
    return [b["type"] for b in blocks]


def text_of(block):
    return plain_text(block[block["type"]]["rich_text"])


def test_headings_lists_and_paragraphs():
    md = "# 제목\n## 소제목\n#### 깊은 제목\n- 글머리\n1. 번호\n> 인용\n첫 줄\n둘째 줄\n\n새 문단"
    blocks = markdown_to_blocks(md)
    assert types(blocks) == ["heading_1", "heading_2", "heading_3", "bulleted_list_item",
                             "numbered_list_item", "quote", "paragraph", "paragraph"]
    assert text_of(blocks[6]) == "첫 줄\n둘째 줄"


def test_table_skips_separator_and_uses_header():
    blocks = markdown_to_blocks("| 역량 | 경험 |\n|---|---|\n| RAG | 검색 구축 |")
    assert types(blocks) == ["table"]
    table = blocks[0]["table"]
    assert table["table_width"] == 2
    assert table["has_column_header"] is True
    rows = table["children"]
    assert len(rows) == 2
    assert plain_text(rows[1]["table_row"]["cells"][0]) == "RAG"


def test_bold_markers_become_annotations():
    parts = rich_text("앞 **굵게** 뒤")
    assert [p["text"]["content"] for p in parts] == ["앞 ", "굵게", " 뒤"]
    assert parts[1]["annotations"]["bold"] is True


def test_long_text_is_split_not_truncated():
    text = "가" * (MAX_TEXT * 2 + 10)
    parts = rich_text(text)
    assert len(parts) == 3
    assert plain_text(parts) == text


def test_source_comments_are_removed():
    blocks = markdown_to_blocks("문장. <!-- src: a.md --> 다음.")
    assert text_of(blocks[0]) == "문장. 다음."


def test_code_fence():
    blocks = markdown_to_blocks("```\n| 표 아님 |\n```")
    assert types(blocks) == ["code"]
