"""글로 된 자소서 문항을 questions.json 형식으로 바꾼다 (브라우저 창으로 읽은 질문 입력칸 등).

글자수는 문항 문장의 "(최대 500자)", "1,000자 이내" 같은 표기에서 읽는다.
세는 방식은 알 수 없으므로 더 엄격한 공백 포함으로 둔다(question-extract 규칙).
"""

import re

_LIMIT = re.compile(r"([\d,]+)\s*자")


def _limit(text: str) -> int | None:
    matches = _LIMIT.findall(text)
    return int(matches[-1].replace(",", "")) if matches else None


def parse_text_questions(texts: list[str], source: str = "interactive") -> list[dict]:
    questions = []
    for text in (t.strip() for t in texts):
        if not text:
            continue
        questions.append({
            "id": len(questions) + 1,
            "text": text,  # 원문 그대로
            "limit": _limit(text),
            "count_mode": "with_spaces",
            "count_newlines": False,
            "hangul_bytes": 2,
            "source": source,
        })
    return questions
