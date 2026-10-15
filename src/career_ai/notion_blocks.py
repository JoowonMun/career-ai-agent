"""마크다운을 Notion 블록으로 바꾼다. 이 도구의 문서에 쓰이는 문법만 다룬다."""

import re

from career_ai.charcount import normalize

MAX_TEXT = 2000

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_NUMBERED = re.compile(r"^\d+\.\s+(.*)$")


def _text_parts(content: str, bold: bool) -> list[dict]:
    parts = []
    for start in range(0, len(content), MAX_TEXT):
        part = {"type": "text", "text": {"content": content[start:start + MAX_TEXT]}}
        if bold:
            part["annotations"] = {"bold": True}
        parts.append(part)
    return parts


def rich_text(text: str) -> list[dict]:
    pieces = text.split("**")
    if len(pieces) % 2 == 0:  # 짝이 맞지 않는 ** 는 글자 그대로 둔다
        pieces = [text]
    parts = []
    for i, piece in enumerate(pieces):
        if piece:
            parts.extend(_text_parts(piece, bold=i % 2 == 1))
    return parts


def plain_text(rich: list[dict]) -> str:
    return "".join(part["text"]["content"] for part in rich)


def _block(kind: str, text: str, **extra) -> dict:
    return {"object": "block", "type": kind, kind: {"rich_text": rich_text(text), **extra}}


def paragraph(text: str) -> dict:
    return _block("paragraph", text)


def heading(level: int, text: str, toggle: bool = False) -> dict:
    return _block(f"heading_{level}", text, is_toggleable=toggle)


def bullet(text: str) -> dict:
    return _block("bulleted_list_item", text)


def numbered(text: str) -> dict:
    return _block("numbered_list_item", text)


def quote(text: str) -> dict:
    return _block("quote", text)


def callout(emoji: str, text: str) -> dict:
    return _block("callout", text, icon={"type": "emoji", "emoji": emoji})


def code(text: str) -> dict:
    return _block("code", text, language="plain text")


def divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def table(rows: list[list[str]]) -> dict:
    width = max(len(row) for row in rows)
    children = [
        {"object": "block", "type": "table_row",
         "table_row": {"cells": [rich_text(cell) for cell in row + [""] * (width - len(row))]}}
        for row in rows
    ]
    return {"object": "block", "type": "table", "table": {
        "table_width": width, "has_column_header": True, "has_row_header": False,
        "children": children,
    }}


def _is_separator(cells: list[str]) -> bool:
    return all(cell and set(cell) <= set("-: ") for cell in cells)


def markdown_to_blocks(md: str) -> list[dict]:
    blocks: list[dict] = []
    paragraph_lines: list[str] = []
    table_rows: list[list[str]] = []
    code_lines: list[str] | None = None

    def flush_paragraph():
        if paragraph_lines:
            blocks.append(paragraph("\n".join(paragraph_lines)))
            paragraph_lines.clear()

    def flush_table():
        if table_rows:
            blocks.append(table(list(table_rows)))
            table_rows.clear()

    for line in normalize(md).split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            if code_lines is None:
                flush_paragraph()
                flush_table()
                code_lines = []
            else:
                blocks.append(code("\n".join(code_lines)))
                code_lines = None
            continue
        if code_lines is not None:
            code_lines.append(line)
            continue
        if stripped.startswith("|"):
            flush_paragraph()
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if not _is_separator(cells):
                table_rows.append(cells)
            continue
        flush_table()
        if not stripped:
            flush_paragraph()
            continue
        if match := _HEADING.match(stripped):
            flush_paragraph()
            blocks.append(heading(min(len(match.group(1)), 3), match.group(2)))
        elif stripped.startswith(("- ", "* ")):
            flush_paragraph()
            blocks.append(bullet(stripped[2:]))
        elif match := _NUMBERED.match(stripped):
            flush_paragraph()
            blocks.append(numbered(match.group(1)))
        elif stripped.startswith(">"):
            flush_paragraph()
            blocks.append(quote(stripped.lstrip(">").strip()))
        else:
            paragraph_lines.append(stripped)
    flush_paragraph()
    flush_table()
    if code_lines:
        blocks.append(code("\n".join(code_lines)))
    return blocks
