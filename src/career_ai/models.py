"""지원 폴더의 파일 형식."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

CountMode = Literal["with_spaces", "without_spaces", "bytes"]
QuestionSource = Literal["posting", "platform", "paste", "screenshot", "interactive", "free"]


class Question(BaseModel):
    id: int = Field(ge=1)
    text: str
    limit: int | None = Field(default=None, ge=1)
    # 세는 방식은 추측하지 않는다. 문항에서 확인했거나 사용자가 정한 값만 들어온다.
    count_mode: CountMode
    count_newlines: bool = False
    hangul_bytes: Literal[2, 3] = 2
    source: QuestionSource


class QuestionSet(BaseModel):
    questions: list[Question] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "QuestionSet":
        # Windows PowerShell 5.1은 UTF-8 파일에 BOM을 붙인다.
        return cls.model_validate_json(path.read_text(encoding="utf-8-sig"))


class Posting(BaseModel):
    """검색으로 모은 공고 한 건. 공고에 없는 값은 None으로 두고 짐작하지 않는다."""

    posting_id: str  # "{수집원}-{원래 공고 번호}"
    platform: Literal["사람인", "고용24"]
    company: str
    title: str
    url: str
    location: str | None = None
    remote: bool = False  # 전면 재택이라고 적힌 공고
    employment_type: str | None = None
    experience: str | None = None
    industry: str | None = None
    keywords: str | None = None
    salary: str | None = None  # 공고에 적힌 그대로
    salary_min_10k_krw: int | None = None  # 연봉으로 적힌 경우만, 만원 단위
    salary_max_10k_krw: int | None = None
    posted: str | None = None  # YYYY-MM-DD
    deadline: str | None = None
