"""공고 페이지 한 건 읽기 (Playwright). 로그인·입력·제출은 하지 않고 화면의 글자만 읽는다."""

import re
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

PROFILE_DIR = Path.home() / ".career-ai" / "browser-profile"
LOAD_TIMEOUT_MS = 30_000
IDLE_TIMEOUT_MS = 10_000
INTERACTIVE_MAX_SECONDS = 540  # Claude Code의 명령 제한(10분)보다 짧게
# 비밀번호 칸이 있어도 본문이 이만큼 길면 공고 페이지로 본다(헤더 로그인 폼 등).
LOGIN_WALL_MAX_CHARS = 1500
# 이보다 세로로 긴 이미지는 공고 상세로 본다(로고·배너 제외). 예: 잡코리아 상세요강 958×6009.
MIN_POSTING_IMAGE_HEIGHT = 600
_IMAGE_SIZES = "els => els.map(e => [e.src, e.naturalHeight])"
_LOGIN_PATH = re.compile(r"(^|/)(login|signin|sign-in|sign_in|auth)(/|$|\.)", re.IGNORECASE)


def is_login_wall(url: str, text: str, has_password: bool) -> bool:
    if _LOGIN_PATH.search(urlparse(url).path):
        return True
    return has_password and len(text) < LOGIN_WALL_MAX_CHARS


def clean_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def read_form_questions(tab) -> list[str] | None:
    """자소서 작성 화면의 질문 입력칸(textarea.qna-question) 값. 입력칸이 없으면 [].

    사이트가 선택을 막아 둔(unselectable) 문항은 읽지 않고 None을 돌려준다.
    """
    boxes = tab.locator("textarea.qna-question")
    values = []
    for i in range(boxes.count()):
        box = boxes.nth(i)
        if "unselectable" in (box.get_attribute("class") or "").split():
            return None
        values.append(box.input_value().strip())
    return [v for v in values if v]


def read_frames(tab) -> tuple[str, list[str]]:
    """iframe까지 포함한 본문 텍스트와 공고 이미지 주소. 상세요강을 iframe에 넣는 사이트가 많다."""
    texts, image_urls = [], []
    for frame in tab.frames:
        try:
            text = clean_text(frame.inner_text("body"))
            sizes = frame.eval_on_selector_all("img", _IMAGE_SIZES)
        except PlaywrightError:
            continue  # 광고 프레임 등이 읽는 중에 사라짐
        if text:
            texts.append(text)
        for src, height in sizes:
            if height >= MIN_POSTING_IMAGE_HEIGHT and src not in image_urls:
                image_urls.append(src)
    return "\n\n".join(texts), image_urls


def fetch(url: str, save_html: Path | None = None) -> dict:
    """페이지 본문 텍스트와 공고 이미지 주소. parser는 항상 generic이다(사이트 전용 파서 없음)."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            tab = browser.new_page(locale="ko-KR")
            tab.goto(url, wait_until="domcontentloaded", timeout=LOAD_TIMEOUT_MS)
            try:
                tab.wait_for_load_state("networkidle", timeout=IDLE_TIMEOUT_MS)
            except PlaywrightError:
                pass  # 광고 등으로 네트워크가 계속 쓰이면 그대로 읽는다.
            text, image_urls = read_frames(tab)
            has_password = tab.locator("input[type=password]").count() > 0
            final_url = tab.url
            if save_html:
                save_html.write_text(tab.content(), encoding="utf-8")
        finally:
            browser.close()
    if is_login_wall(final_url, text, has_password):
        return {"error": "login_wall", "url": final_url}
    return {"url": final_url, "parser": "generic", "posting_text": text, "questions": [],
            "image_urls": image_urls}


def interactive(url: str, profile: Path = PROFILE_DIR) -> dict:
    """보이는 브라우저로 연다. 사용자가 로그인해 문항 화면으로 간 뒤 창을 닫으면
    닫기 직전 화면의 텍스트를 돌려준다. 로그인 상태는 도구 전용 프로필에 남는다.

    거쳐 간 페이지(예: 공고 페이지)의 글자는 earlier_pages에, 자소서 작성 화면의 질문 입력칸 값은
    form_questions에 담는다(자동 접속이 막힌 사이트에서 문항을 읽을 때).
    """
    profile.mkdir(parents=True, exist_ok=True)
    last = {"url": url, "page_text": ""}
    visited: dict[str, str] = {}  # 앞서 본 페이지(예: 공고 페이지) → 글자
    form_questions: list[str] = []
    locked = False
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(profile, headless=False, locale="ko-KR")
        try:
            tab = context.pages[0] if context.pages else context.new_page()
            tab.goto(url, wait_until="domcontentloaded", timeout=LOAD_TIMEOUT_MS)
            deadline = time.monotonic() + INTERACTIVE_MAX_SECONDS
            while context.pages and time.monotonic() < deadline:
                tab = context.pages[-1]  # 새 탭에서 문항을 열었으면 그 탭
                try:
                    current = {"url": tab.url, "page_text": clean_text(tab.inner_text("body"))}
                    if last["page_text"] and last["url"] != current["url"]:
                        visited[last["url"]] = last["page_text"]
                    last = current
                    found = read_form_questions(tab)
                    if found is None:
                        locked = True
                    elif found:
                        form_questions, locked = found, False
                    tab.wait_for_timeout(1000)
                except PlaywrightError:
                    pass  # 창을 닫는 중
        finally:
            try:
                context.close()
            except PlaywrightError:
                pass
    visited.pop(last["url"], None)
    return {
        **last,
        "earlier_pages": [{"url": u, "page_text": t} for u, t in visited.items()],
        "form_questions": form_questions,
        "questions_locked": locked,
    }
