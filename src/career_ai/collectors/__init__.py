"""수집원 공통: 재택 여부와 연봉 문구 해석."""

import re

REMOTE = re.compile(r"(전면|풀|완전|100%)\s*재택|full[\s-]*remote", re.IGNORECASE)
_NUMBER = re.compile(r"\d[\d,]*")


def is_remote(*texts: str | None) -> bool:
    return any(REMOTE.search(t) for t in texts if t)


def parse_salary(text: str | None) -> tuple[int | None, int | None]:
    """연봉 문구에서 (하한, 상한) 만원. 'N만원 이상'은 상한을 모르는 것으로 본다."""
    if "만원" not in (text or "").replace(" ", ""):
        return None, None
    numbers = [int(n.replace(",", "")) for n in _NUMBER.findall(text)]
    if len(numbers) >= 2:
        return numbers[0], numbers[1]
    if len(numbers) == 1:
        return numbers[0], None if "이상" in text else numbers[0]
    return None, None
