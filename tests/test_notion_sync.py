import itertools
import json
import shutil
from pathlib import Path

import pytest

from career_ai.config import REPO_ROOT
from career_ai.notion_api import NotionError
from career_ai.notion_blocks import paragraph, plain_text
from career_ai.notion_sync import (
    MEMO_HEADING,
    build_auto_blocks,
    build_properties,
    init_database,
    push,
    read_frontmatter,
    split_sections,
)

SAMPLE = REPO_ROOT / "examples" / "sample-data" / "applications" / "샘플전자_S001"


@pytest.fixture
def app(tmp_path) -> Path:
    target = tmp_path / "샘플전자_S001"
    shutil.copytree(SAMPLE, target)
    return target


def heading_texts(items):
    return [plain_text(b[b["type"]]["rich_text"]) for b, _ in items
            if b["type"].startswith("heading")]


def test_frontmatter_ignores_comments():
    text = ("---\nrole:        # AI 엔지니어 | AX\nurl: https://x.com/a#b\n"
            "deadline: 2026-11-30\n---\n본문")
    assert read_frontmatter(text) == {
        "role": "", "url": "https://x.com/a#b", "deadline": "2026-11-30",
    }


def test_split_sections():
    assert split_sections("# 제목\n## 요약\n- a\n## 적합도: 상\n근거")["요약"] == "- a"


def test_build_properties_from_sample(app):
    posting_id, props = build_properties(app)
    assert posting_id == "S001"
    title = props["이름"]["title"][0]["text"]["content"]
    assert title == "샘플전자 | AI 엔지니어 (LLM 서비스) 경력 채용"
    assert props["적합도"] == {"select": {"name": "상"}}
    assert props["마감일"] == {"date": {"start": "2026-11-30"}}
    assert props["공고 URL"] == {"url": None}
    assert props["문항 수"] == {"number": 2}
    assert props["자소서"] == {"checkbox": True}
    assert "상태" not in props and "공고ID" not in props


def test_missing_posting_id_raises(app):
    path = app / "posting.md"
    text = path.read_text(encoding="utf-8").replace("posting_id: S001", "posting_id: ")
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="posting_id"):
        build_properties(app)


def test_auto_blocks_order(app):
    assert heading_texts(build_auto_blocks(app))[:8] == [
        "🤖 자동 생성", "기업 분석", "직무 분석", "강조 전략", "자기소개서",
        "Q1. 샘플전자에 지원한 동기와 입사 후 하고 싶은 일을 작성해 주세요.",
        "Q2. 데이터나 모델의 품질 문제를 해결한 경험을 작성해 주세요.", "경력기술서",
    ]


def test_no_essay_section_without_final(app):
    (app / "final.md").unlink()
    assert "자기소개서" not in heading_texts(build_auto_blocks(app))


class FakeNotion:
    """블록 트리와 페이지 속성을 메모리에 들고 있는 가짜 Notion."""

    def __init__(self):
        self.ids = (f"b{n}" for n in itertools.count())
        self.children: dict[str, list[dict]] = {}
        self.pages: dict[str, dict] = {}
        self.updates: list[dict] = []
        self.deleted: list[str] = []
        self.trashed: set[str] = set()

    def create_database(self, parent_page_id, title, properties):
        self.schema = properties
        return {"id": "db1", "url": "https://notion.so/db1", "data_sources": [{"id": "ds1"}]}

    def find_page(self, data_source_id, prop, value):
        for page_id, props in self.pages.items():
            if page_id in self.trashed:
                continue
            if props["공고ID"]["rich_text"][0]["text"]["content"] == value:
                return {"id": page_id}
        return None

    def create_page(self, data_source_id, properties):
        page_id = next(self.ids)
        self.pages[page_id] = dict(properties)
        self.children[page_id] = []
        return {"id": page_id, "url": f"https://notion.so/{page_id}"}

    def update_page(self, page_id, properties):
        if page_id in self.trashed:
            raise NotionError("Notion API 400 validation_error: Can't edit block that is archived.",
                              status=400)
        self.updates.append(properties)
        self.pages[page_id].update(properties)
        return {"id": page_id, "url": f"https://notion.so/{page_id}"}

    def list_children(self, block_id):
        return list(self.children[block_id])

    def append_children(self, block_id, children, position=None):
        created = []
        for block in children:
            block = {**block, "id": next(self.ids)}
            self.children[block["id"]] = []
            created.append(block)
        siblings = self.children[block_id]
        if position is None:
            index = len(siblings)
        elif position["type"] == "start":
            index = 0
        else:
            index = [b["id"] for b in siblings].index(position["after_block"]["id"]) + 1
        siblings[index:index] = created
        # 실제 Notion은 새 블록만이 아니라 부모의 자식 전체 목록을 돌려준다 (2026-10-14 확인).
        return list(siblings)

    def delete_block(self, block_id):
        self.deleted.append(block_id)
        for siblings in self.children.values():
            siblings[:] = [b for b in siblings if b["id"] != block_id]


def top_texts(fake, page_id):
    out = []
    for block in fake.children[page_id]:
        rich = block[block["type"]].get("rich_text")
        out.append(plain_text(rich) if rich is not None else block["type"])
    return out


def test_init_database_returns_data_source():
    fake = FakeNotion()
    result = init_database(fake, "parent")
    assert result["data_source_id"] == "ds1"
    assert fake.schema["상태"]["select"]["options"][1] == {"name": "작성 중"}


def test_first_push_creates_page_with_memo_last(app):
    fake = FakeNotion()
    result = push(app, fake, "ds1")
    page = result["page_id"]
    assert result["created"] is True
    assert fake.pages[page]["상태"] == {"select": {"name": "작성 중"}}
    texts = top_texts(fake, page)
    assert texts[0] == "요약"
    assert texts[-2:] == [MEMO_HEADING, ""]
    assert texts.index("경력기술서") < texts.index(MEMO_HEADING)
    assert json.loads((app / "notion.json").read_text(encoding="utf-8"))["page_id"] == page


def test_repush_keeps_memo_and_status(app):
    fake = FakeNotion()
    page = push(app, fake, "ds1")["page_id"]
    fake.append_children(page, [paragraph("면접 질문 메모")])
    fake.pages[page]["상태"] = {"select": {"name": "제출 완료"}}

    result = push(app, fake, "ds1")

    texts = top_texts(fake, page)
    assert result["created"] is False
    assert texts.count("요약") == 1
    assert texts[-1] == "면접 질문 메모"
    assert fake.pages[page]["상태"] == {"select": {"name": "제출 완료"}}
    assert all("상태" not in u and "공고ID" not in u for u in fake.updates)


def test_push_without_state_file_finds_existing_page(app):
    fake = FakeNotion()
    page = push(app, fake, "ds1")["page_id"]
    (app / "notion.json").unlink()

    result = push(app, fake, "ds1")

    assert result["page_id"] == page
    assert len(fake.pages) == 1


def test_trashed_page_is_replaced_by_new_page(app):
    fake = FakeNotion()
    old = push(app, fake, "ds1")["page_id"]
    fake.trashed.add(old)

    result = push(app, fake, "ds1")

    assert result["created"] is True
    assert result["page_id"] != old


def test_state_from_other_data_source_is_ignored(app):
    fake = FakeNotion()
    push(app, fake, "ds1")
    other = FakeNotion()

    result = push(app, other, "ds2")

    assert result["created"] is True
    state = json.loads((app / "notion.json").read_text(encoding="utf-8"))
    assert state["data_source_id"] == "ds2"


def test_state_file_without_page_id_is_tolerated(app):
    (app / "notion.json").write_text("{}", encoding="utf-8")
    assert push(app, FakeNotion(), "ds1")["created"] is True


def test_missing_memo_heading_stops_without_deleting(app):
    fake = FakeNotion()
    page = push(app, fake, "ds1")["page_id"]
    memo = next(b for b in fake.children[page] if b["type"] == "heading_2"
                and plain_text(b["heading_2"]["rich_text"]) == MEMO_HEADING)
    fake.delete_block(memo["id"])
    fake.deleted.clear()

    with pytest.raises(ValueError, match="내 메모"):
        push(app, fake, "ds1")
    assert fake.deleted == []


def test_toggle_children_are_attached(app):
    fake = FakeNotion()
    page = push(app, fake, "ds1")["page_id"]
    toggle = next(b for b in fake.children[page] if b["type"] == "heading_2"
                  and plain_text(b["heading_2"]["rich_text"]) == "직무 분석")
    assert any(child["type"] == "table" for child in fake.children[toggle["id"]])
