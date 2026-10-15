"""사람인 채용공고 API (https://oapi.saramin.co.kr)."""

import html
from datetime import date, datetime, time, timedelta, timezone

import httpx

from career_ai.collectors import is_remote, parse_salary
from career_ai.http import get
from career_ai.models import Posting

API = "https://oapi.saramin.co.kr/job-search"
COUNT = 110  # 한 번에 받을 수 있는 최대 개수
KST = timezone(timedelta(hours=9))


def _date(timestamp: str) -> str | None:
    return datetime.fromtimestamp(int(timestamp), KST).date().isoformat() if timestamp else None


def parse(data: dict) -> list[Posting]:
    postings = []
    for job in data["jobs"]["job"]:
        position = job["position"]
        location = html.unescape(position["location"]["name"])
        salary = job["salary"]["name"]
        low, high = parse_salary(salary)
        postings.append(Posting(
            posting_id=f"saramin-{job['id']}",
            platform="사람인",
            company=job["company"]["detail"]["name"],
            title=position["title"],
            url=job["url"],
            location=location,
            remote=is_remote(position["title"], location),
            employment_type=position["job-type"]["name"] or None,
            experience=position["experience-level"]["name"] or None,
            industry=position["industry"]["name"] or None,
            keywords=job.get("keyword") or None,
            salary=salary,
            salary_min_10k_krw=low,
            salary_max_10k_krw=high,
            posted=_date(job["posting-timestamp"]),
            deadline=_date(job["expiration-timestamp"]),
        ))
    return postings


def search(client: httpx.Client, key: str, keywords: str, since: date | None,
           *, backoff: float = 1.0) -> list[Posting]:
    params = {"access-key": key, "keywords": keywords, "count": COUNT, "sort": "pd"}
    if since:
        params["published_min"] = int(datetime.combine(since, time(), KST).timestamp())
    response = get(client, API, params=params, headers={"Accept": "application/json"},
                   backoff=backoff)
    data = response.json()
    if "jobs" not in data:
        raise ValueError(f"사람인 응답 오류: {data}")
    return parse(data)
