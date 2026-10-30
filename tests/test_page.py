from pathlib import Path

import pytest

from career_ai.collectors import page

PAGES = Path(__file__).parent / "fixtures" / "pages"


@pytest.mark.parametrize(("url", "text", "has_password", "expected"), [
    ("https://site.test/login?next=/job/1", "아이디 비밀번호", True, True),
    ("https://site.test/member/signin", "본문 " * 1000, False, True),
    ("https://site.test/job/1", "로그인", True, True),
    ("https://site.test/job/1", "공고 본문 " * 400, True, False),
    ("https://site.test/job/1", "공고 본문", False, False),
    ("https://site.test/blog/authors-pick", "공고 본문", False, False),
])
def test_is_login_wall(url, text, has_password, expected):
    assert page.is_login_wall(url, text, has_password) is expected


def test_clean_text_collapses_blank_lines():
    assert page.clean_text("  a  \n\n\n\n b\t\n") == "a\n\nb"


@pytest.fixture(scope="module")
def browser_ok():
    from playwright.sync_api import Error, sync_playwright

    try:
        with sync_playwright() as pw:
            pw.chromium.launch().close()
    except Error as e:
        pytest.skip(f"Chromium을 띄울 수 없습니다 (uv run playwright install chromium): {e}")


def test_fetch_reads_rendered_text(browser_ok, tmp_path):
    saved = tmp_path / "page.html"
    result = page.fetch((PAGES / "posting.html").as_uri(), save_html=saved)
    assert result["parser"] == "generic"
    assert result["questions"] == []
    text = result["posting_text"]
    assert "샘플전자 AI 엔지니어 채용" in text
    assert "스크립트로 그린 마감일 2026-11-30" in text
    assert "숨겨진 글" not in text
    assert "\n\n\n" not in text
    assert "샘플전자" in saved.read_text(encoding="utf-8")


def test_fetch_detects_login_wall(browser_ok):
    result = page.fetch((PAGES / "login.html").as_uri())
    assert result["error"] == "login_wall"


def _open(path):
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.launch()
    tab = browser.new_page()
    tab.goto(path.as_uri())
    return pw, browser, tab


def test_read_form_questions_from_textareas(browser_ok):
    pw, browser, tab = _open(PAGES / "form-questions.html")
    try:
        assert page.read_form_questions(tab) == [
            "1. 지원 동기를 작성하세요 (최대 700자)", "2. 협업 경험 (1,000자 이내)",
        ]
    finally:
        browser.close()
        pw.stop()


def test_locked_questions_are_not_read(browser_ok):
    pw, browser, tab = _open(PAGES / "form-locked.html")
    try:
        assert page.read_form_questions(tab) is None
    finally:
        browser.close()
        pw.stop()


def test_page_without_question_boxes_returns_empty(browser_ok):
    pw, browser, tab = _open(PAGES / "posting.html")
    try:
        assert page.read_form_questions(tab) == []
    finally:
        browser.close()
        pw.stop()


def _png(path, width, height):
    from PIL import Image

    Image.new("RGB", (width, height), "white").save(path)


def test_fetch_reads_iframe_text_and_large_images(browser_ok, tmp_path):
    _png(tmp_path / "tall.png", 600, 2000)
    _png(tmp_path / "logo.png", 120, 60)
    (tmp_path / "inner.html").write_text(
        '<html><body><p>상세요강 본문</p><img src="tall.png"><img src="tall.png">'
        '<img src="logo.png"></body></html>', encoding="utf-8")
    (tmp_path / "outer.html").write_text(
        '<html><body><h1>모집요강 요약</h1><img src="logo.png">'
        '<iframe src="inner.html"></iframe></body></html>', encoding="utf-8")

    result = page.fetch((tmp_path / "outer.html").as_uri())

    assert "모집요강 요약" in result["posting_text"]
    assert "상세요강 본문" in result["posting_text"]
    assert result["image_urls"] == [(tmp_path / "tall.png").as_uri()]
