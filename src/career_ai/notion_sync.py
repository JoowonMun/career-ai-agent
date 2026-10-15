"""지원 폴더를 Notion "지원 현황" 데이터베이스의 페이지로 옮긴다."""

import json
import re
from pathlib import Path

from career_ai.models import QuestionSet
from career_ai.notion_api import NotionError
from career_ai.notion_blocks import (
    callout,
    divider,
    heading,
    markdown_to_blocks,
    paragraph,
    rich_text,
)

DATABASE_TITLE = "지원 현황"
MEMO_HEADING = "✍️ 내 메모"
AUTO_HEADING = "🤖 자동 생성"
BATCH = 100


def _select_options(*names: str) -> dict:
    return {"select": {"options": [{"name": name} for name in names]}}


DATABASE_PROPERTIES = {
    "이름": {"title": {}},
    "회사": {"rich_text": {}},
    "직무": _select_options("AI 엔지니어", "AX", "데이터 분석", "데이터 사이언티스트", "기타"),
    "상태": _select_options("후보", "작성 중", "검토 중", "제출 완료", "서류 합격", "불합격",
                          "보류"),
    "마감일": {"date": {}},
    "플랫폼": _select_options("자소설닷컴", "잡코리아", "사람인", "고용24", "리멤버", "캐치",
                           "기업 채용 사이트"),
    "공고 URL": {"url": {}},
    "적합도": _select_options("상", "중", "하"),
    "문항 수": {"number": {"format": "number"}},
    "자소서": {"checkbox": {}},
    "공고ID": {"rich_text": {}},
}

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FIT = re.compile(r"^##\s*적합도\s*[:：]\s*(상|중|하)", re.MULTILINE)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig") if path.exists() else ""


def read_frontmatter(text: str) -> dict[str, str]:
    lines = text.lstrip("﻿").split("\n")
    if not lines or lines[0].strip() != "---":
        return {}
    values = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        value = "" if value.startswith("#") else value.split(" #", 1)[0].strip()
        values[key.strip()] = value
    return values


def split_sections(md: str) -> dict[str, str]:
    sections, title, body = {}, None, []
    for line in md.split("\n"):
        if line.startswith("## "):
            if title is not None:
                sections[title] = "\n".join(body).strip()
            title, body = line[3:].strip(), []
        elif title is not None:
            body.append(line)
    if title is not None:
        sections[title] = "\n".join(body).strip()
    return sections


def _select(name: str) -> dict:
    return {"select": {"name": name} if name else None}


def build_properties(app_dir: Path) -> tuple[str, dict]:
    posting = read_frontmatter(_read(app_dir / "posting.md"))
    posting_id = posting.get("posting_id", "")
    if not posting_id:
        raise ValueError(f"posting.md에 posting_id가 없습니다: {app_dir}")
    questions_path = app_dir / "questions.json"
    count = len(QuestionSet.load(questions_path).questions) if questions_path.exists() else 0
    fit = _FIT.search(_read(app_dir / "analysis.md"))
    deadline = posting.get("deadline", "")
    url = posting.get("url", "")
    company, title = posting.get("company", ""), posting.get("title", "")
    return posting_id, {
        "이름": {"title": rich_text(f"{company} | {title}")},
        "회사": {"rich_text": rich_text(company)},
        "직무": _select(posting.get("role", "")),
        "마감일": {"date": {"start": deadline} if _DATE.match(deadline) else None},
        "플랫폼": _select(posting.get("platform", "")),
        "공고 URL": {"url": url if url.startswith("http") else None},
        "적합도": _select(fit.group(1) if fit else ""),
        "문항 수": {"number": count},
        "자소서": {"checkbox": count > 0},
    }


def _shift_headings(md: str) -> str:
    """자동 생성 영역의 제목 2 아래에 들어가도록 '## '를 '### '로 내린다."""
    return re.sub(r"^## ", "### ", md, flags=re.MULTILINE)


def build_auto_blocks(app_dir: Path) -> list[tuple[dict, list[dict]]]:
    analysis = split_sections(_read(app_dir / "analysis.md"))
    career = split_sections(_read(app_dir / "career.md"))
    job_keys = [k for k in analysis if "직무" in k or k.startswith("적합도")]
    company_keys = [k for k in analysis if k != "요약" and k not in job_keys]

    def sections_md(keys: list[str]) -> str:
        return "\n\n".join(f"### {key}\n{analysis[key]}" for key in keys)

    items: list[tuple[dict, list[dict]]] = [
        (callout("📌", "요약"), markdown_to_blocks(analysis.get("요약", ""))),
        (divider(), []),
        (heading(2, AUTO_HEADING), []),
        (heading(2, "기업 분석", toggle=True), markdown_to_blocks(sections_md(company_keys))),
        (heading(2, "직무 분석", toggle=True), markdown_to_blocks(sections_md(job_keys))),
        (heading(2, "강조 전략", toggle=True), markdown_to_blocks(career.get("강조 전략", ""))),
    ]
    final = _read(app_dir / "final.md")
    if final:
        body = "\n".join(line for line in final.split("\n") if not line.startswith("# "))
        items.append((heading(2, "자기소개서"), []))
        items.extend((block, []) for block in markdown_to_blocks(_shift_headings(body)))
    if career.get("맞춤 경력기술서"):
        items.append((heading(2, "경력기술서"), []))
        items.extend((block, []) for block in markdown_to_blocks(career["맞춤 경력기술서"]))
    return items


def memo_blocks() -> list[dict]:
    return [divider(), heading(2, MEMO_HEADING), paragraph("")]


def init_database(client, parent_page_id: str) -> dict:
    database = client.create_database(parent_page_id, DATABASE_TITLE, DATABASE_PROPERTIES)
    return {
        "database_id": database["id"],
        "data_source_id": database["data_sources"][0]["id"],
        "url": database.get("url"),
    }


def _batches(blocks: list) -> list[list]:
    return [blocks[i:i + BATCH] for i in range(0, len(blocks), BATCH)]


def _heading_text(block: dict) -> str:
    if block.get("type") != "heading_2":
        return ""
    return "".join(part.get("plain_text") or part["text"]["content"]
                   for part in block["heading_2"]["rich_text"])


def _clear_auto_section(client, page_id: str) -> int:
    blocks = client.list_children(page_id)
    memo_index = next((i for i, b in enumerate(blocks) if _heading_text(b) == MEMO_HEADING), None)
    if memo_index is None:
        raise ValueError(
            f"페이지에서 '{MEMO_HEADING}' 제목을 찾을 수 없어 자동 영역을 구분할 수 없습니다. "
            f"페이지에 제목 2 블록 '{MEMO_HEADING}'를 다시 만든 뒤 다시 실행하세요."
        )
    end = memo_index
    if memo_index and blocks[memo_index - 1]["type"] == "divider":
        end = memo_index - 1
    for block in blocks[:end]:
        client.delete_block(block["id"])
    return end


def _insert_auto(client, page_id: str, items: list[tuple[dict, list[dict]]]) -> None:
    # 블록 추가 응답은 부모의 자식 전체 목록이라, 추가 전후를 비교해 새 블록을 찾는다.
    known = {block["id"] for block in client.list_children(page_id)}
    created: list[dict] = []
    for batch in _batches([block for block, _ in items]):
        position = ({"type": "after_block", "after_block": {"id": created[-1]["id"]}}
                    if created else {"type": "start"})
        client.append_children(page_id, batch, position)
        new = [block for block in client.list_children(page_id) if block["id"] not in known]
        known.update(block["id"] for block in new)
        created.extend(new)
    if len(created) != len(items):
        raise ValueError("Notion이 돌려준 블록 수가 보낸 블록 수와 다릅니다.")
    for (_, children), parent in zip(items, created, strict=True):
        for batch in _batches(children):
            client.append_children(parent["id"], batch)


def _update_if_alive(client, page_id: str, properties: dict) -> dict | None:
    """페이지를 갱신한다. 지워졌거나 휴지통에 있으면 None."""
    try:
        return client.update_page(page_id, properties)
    except NotionError as e:
        message = str(e).lower()
        if e.status == 404 or "archived" in message or "trash" in message:
            return None
        raise


def _stored_page_id(state_path: Path, data_source_id: str) -> str | None:
    if not state_path.exists():
        return None
    try:
        state = json.loads(_read(state_path))
    except ValueError:
        return None
    # 데이터베이스를 새로 만들었으면 예전 페이지 기록은 쓰지 않는다.
    if state.get("data_source_id") != data_source_id:
        return None
    return state.get("page_id")


def push(app_dir: Path, client, data_source_id: str) -> dict:
    posting_id, properties = build_properties(app_dir)
    items = build_auto_blocks(app_dir)
    state_path = app_dir / "notion.json"

    page_id = _stored_page_id(state_path, data_source_id)
    page = _update_if_alive(client, page_id, properties) if page_id else None
    if page is None:
        found = client.find_page(data_source_id, "공고ID", posting_id)
        page = _update_if_alive(client, found["id"], properties) if found else None

    created = page is None
    removed = 0
    if created:
        page = client.create_page(data_source_id, {
            **properties,
            "상태": {"select": {"name": "작성 중"}},
            "공고ID": {"rich_text": rich_text(posting_id)},
        })
        client.append_children(page["id"], memo_blocks())
    else:
        removed = _clear_auto_section(client, page["id"])
    page_id = page["id"]
    _insert_auto(client, page_id, items)

    state = {"page_id": page_id, "url": page.get("url"), "data_source_id": data_source_id}
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8", newline="\n")
    return {**state, "created": created, "removed_blocks": removed}
