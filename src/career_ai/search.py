"""공고 검색: 사람인·고용24 결과를 공통 형식으로 모으고 중복을 지운 뒤 _inbox에 저장한다."""

import json
import re
from datetime import date, timedelta
from pathlib import Path

import httpx

from career_ai.collectors import saramin, work24
from career_ai.models import Posting

# (이름, .env 키, 모듈). 키가 없는 수집원은 건너뛴다.
SOURCES = (
    ("사람인", "SARAMIN_API_KEY", saramin),
    ("고용24", "WORK24_API_KEY", work24),
)
def _key(posting: Posting) -> tuple[str, str]:
    company = re.sub(r"\(주\)|㈜|주식회사", "", posting.company)
    return re.sub(r"\W", "", company), re.sub(r"\W", "", posting.title)


def dedup(postings: list[Posting]) -> list[Posting]:
    seen, result = set(), []
    for p in postings:
        if _key(p) not in seen:
            seen.add(_key(p))
            result.append(p)
    return result


def search(
    client: httpx.Client,
    keywords: list[str],
    keys: dict[str, str],
    *,
    since_days: int | None = None,
    today: date | None = None,
    backoff: float = 1.0,
) -> dict:
    since = (today or date.today()) - timedelta(days=since_days) if since_days else None
    postings, skipped = [], []
    for name, key_name, source in SOURCES:
        key = keys.get(key_name)
        if not key:
            skipped.append({"source": name, "reason": f"{key_name} 없음"})
            continue
        try:
            postings += source.search(client, key, " ".join(keywords), since, backoff=backoff)
        except Exception as e:  # noqa: BLE001 — 한 수집원의 예상 못 한 응답이 다른 수집원을 막으면 안 된다
            skipped.append({"source": name, "reason": f"{type(e).__name__}: {e}"})
    if since:
        postings = [p for p in postings if not p.posted or p.posted >= since.isoformat()]
    return {"postings": [p.model_dump() for p in dedup(postings)], "skipped": skipped}


def save_inbox(data_dir: Path, postings: list[dict], today: date | None = None) -> Path:
    """같은 날 다시 검색하면 공고ID 기준으로 합친다."""
    path = data_dir / "applications" / "_inbox" / f"{(today or date.today()).isoformat()}.json"
    saved = []
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8-sig"))["postings"]
    ids = {p["posting_id"] for p in saved}
    merged = saved + [p for p in postings if p["posting_id"] not in ids]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"postings": merged}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")
    return path
