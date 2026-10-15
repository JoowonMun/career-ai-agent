"""career-ai 명령줄 진입점. 모든 명령은 결과를 JSON으로 stdout에 출력한다."""

import argparse
import importlib
import json
import pkgutil
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

from career_ai import __version__, extensions
from career_ai.charcount import check_application, normalize, write_final
from career_ai.config import (
    REPO_ROOT,
    ConfigError,
    api_keys,
    load_config,
    optional_keys,
    require_setting,
)
from career_ai.data_init import init_data
from career_ai.enrich import company, dart, news
from career_ai.filters import apply as apply_filters
from career_ai.filters import load_preferences
from career_ai.notion_api import NotionClient, NotionError
from career_ai.notion_sync import init_database, push
from career_ai.search import save_inbox, search


def emit(data: object) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def fail(code: str, message: str) -> int:
    emit({"error": code, "message": message})
    return 2


def cmd_config(args: argparse.Namespace) -> int:
    try:
        config = load_config()
    except ConfigError as e:
        return fail("config", str(e))
    emit({"data_dir": str(config.data_dir)})
    return 0


def resolve_app_dir(raw: str) -> Path:
    path = Path(raw)
    if path.is_dir():
        return path.resolve()
    return load_config().data_dir / "applications" / raw


def cmd_count(args: argparse.Namespace) -> int:
    try:
        app_dir = resolve_app_dir(args.app_dir)
    except ConfigError as e:
        return fail("config", str(e))
    if not (app_dir / "questions.json").exists():
        return fail("not_found", f"questions.json이 없습니다: {app_dir}")
    results = check_application(app_dir)
    final, error = None, None
    if args.write_final:
        try:
            final = str(write_final(app_dir, results))
        except ValueError as e:
            error = str(e)
    emit({"results": results, "final": final, "error": error})
    return 1 if error else 0


def cmd_clean(args: argparse.Namespace) -> int:
    text = Path(args.input).read_text(encoding="utf-8")
    out = Path(args.out)
    out.write_text(normalize(text) + "\n", encoding="utf-8", newline="\n")
    emit({"out": str(out)})
    return 0


def cmd_init_data(args: argparse.Namespace) -> int:
    # CAREER_DATA_DIR와 같은 기준(저장소 루트)으로 상대 경로를 해석한다.
    target = Path(args.target)
    if not target.is_absolute():
        target = REPO_ROOT / target
    emit(init_data(target))
    return 0


def cmd_dart(args: argparse.Namespace) -> int:
    try:
        (key,) = api_keys(("DART_API_KEY",), REPO_ROOT)
    except ConfigError as e:
        return fail("missing_key", str(e))
    try:
        with httpx.Client(timeout=30) as client:
            result = dart.lookup(client, key, name=args.name, corp_code=args.corp_code)
    except dart.DartError as e:
        return fail("dart", str(e))
    except httpx.HTTPError as e:
        return fail("http", str(e))
    emit(result)
    return 0


def cmd_news(args: argparse.Namespace) -> int:
    # 네이버 검색 API는 신규 등록이 막혀 있을 수 있어, 키가 없으면 구글 뉴스 RSS를 쓴다.
    try:
        client_id, secret = api_keys(("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET"), REPO_ROOT)
    except ConfigError:
        client_id = secret = None
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            if client_id:
                items = news.search_news(client, client_id, secret, args.query,
                                         months=args.months)
            else:
                items = news.search_google_news(client, args.query, months=args.months)
    except (httpx.HTTPError, ET.ParseError) as e:
        return fail("http", str(e))
    emit(items)
    return 0


_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_TRAILING_ID = re.compile(r"([0-9a-f]{32})$")
_TOKEN_HINT = "README의 'Notion 연결'을 따라 통합을 만들고 .env에 토큰을 넣어 주세요."


def page_id_from(raw: str) -> str:
    """Notion 페이지 URL(끝의 32자리)이나 ID(대시 포함 가능)에서 페이지 ID를 뽑는다."""
    text = raw.strip().lower().split("?")[0].split("#")[0].rstrip("/")
    if _UUID.match(text):
        return text.replace("-", "")
    match = _TRAILING_ID.search(text)
    if not match:
        raise ValueError(f"Notion 페이지 ID를 찾을 수 없습니다: {raw}")
    return match.group(1)


def cmd_notion_init(args: argparse.Namespace) -> int:
    try:
        token = require_setting("NOTION_TOKEN", _TOKEN_HINT)
        result = init_database(NotionClient(token), page_id_from(args.parent))
    except ConfigError as e:
        return fail("config", str(e))
    except (NotionError, ValueError) as e:
        return fail("notion", str(e))
    next_step = f".env에 NOTION_DATA_SOURCE_ID={result['data_source_id']} 를 추가하세요."
    emit({**result, "next": next_step})
    return 0


def cmd_notion_push(args: argparse.Namespace) -> int:
    try:
        token = require_setting("NOTION_TOKEN", _TOKEN_HINT)
        data_source_id = require_setting(
            "NOTION_DATA_SOURCE_ID",
            "`uv run career-ai notion init --parent <페이지 URL>`의 결과를 넣어 주세요.",
        )
        app_dir = resolve_app_dir(args.app_dir)
        result = push(app_dir, NotionClient(token), data_source_id)
    except ConfigError as e:
        return fail("config", str(e))
    except (NotionError, ValueError) as e:
        return fail("notion", str(e))
    emit(result)
    return 0


SEARCH_KEYS = ("SARAMIN_API_KEY", "WORK24_API_KEY")
COMPANY_KEYS = ("DART_API_KEY", "DATA_GO_KR_API_KEY")


def days(raw: str) -> int:
    match = re.fullmatch(r"(\d+)d", raw)
    if not match:
        raise argparse.ArgumentTypeError("기간은 7d처럼 일 단위로 적어 주세요.")
    return int(match.group(1))


def cmd_search(args: argparse.Namespace) -> int:
    try:
        data_dir = load_config(REPO_ROOT).data_dir
    except ConfigError as e:
        return fail("config", str(e))
    keys = optional_keys(SEARCH_KEYS, REPO_ROOT)
    with httpx.Client(timeout=30) as client:
        result = search(client, args.keywords, keys, since_days=args.since)
    inbox = save_inbox(data_dir, result["postings"])
    emit({"inbox": str(inbox), "count": len(result["postings"]), "skipped": result["skipped"]})
    return 0


def cmd_company(args: argparse.Namespace) -> int:
    try:
        data_dir = load_config(REPO_ROOT).data_dir
    except ConfigError as e:
        return fail("config", str(e))
    keys = optional_keys(COMPANY_KEYS, REPO_ROOT)
    with httpx.Client(timeout=30) as client:
        emit(company.lookup(client, keys, args.name, data_dir / "companies",
                            corp_code=args.corp_code, nps_seq=args.nps_seq))
    return 0


def cmd_filter(args: argparse.Namespace) -> int:
    try:
        data_dir = load_config(REPO_ROOT).data_dir
    except ConfigError as e:
        return fail("config", str(e))
    inbox = Path(args.inbox)
    if not inbox.is_file():
        inbox = data_dir / "applications" / "_inbox" / args.inbox
    prefs_path = data_dir / "preferences.yaml"
    for path in (inbox, prefs_path):
        if not path.is_file():
            return fail("not_found", f"파일이 없습니다: {path}")
    postings = json.loads(inbox.read_text(encoding="utf-8-sig"))["postings"]
    keys = optional_keys(COMPANY_KEYS, REPO_ROOT)
    looked_up: dict[str, dict] = {}

    def company_info(name: str) -> dict:
        # 같은 회사 공고가 여러 개여도 한 번만 조회한다.
        if name not in looked_up:
            looked_up[name] = company.lookup(client, keys, name, data_dir / "companies")
        return looked_up[name]

    with httpx.Client(timeout=30) as client:
        result = apply_filters(postings, load_preferences(prefs_path), company_info)
    emit(result)
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    # 브라우저 의존성은 fetch에서만 불러온다.
    from playwright.sync_api import Error as PlaywrightError

    from career_ai.collectors import page

    try:
        if args.interactive:
            result = page.interactive(args.url)
            if result.get("form_questions"):
                from career_ai.parsers.questions import parse_text_questions

                result["parser"] = "form"
                result["questions"] = parse_text_questions(result["form_questions"])
        else:
            result = page.fetch(args.url, Path(args.save_html) if args.save_html else None)
    except PlaywrightError as e:
        return fail("browser", str(e))
    emit(result)
    return 0 if "error" not in result else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="career-ai")
    parser.add_argument("--version", action="version", version=f"career-ai {__version__}")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("config", help="데이터 폴더 경로 확인")
    p.set_defaults(handler=cmd_config)

    p = sub.add_parser("count", help="지원 폴더의 문항별 글자수 검증")
    p.add_argument("app_dir", help="지원 폴더 경로 또는 applications/ 아래 폴더 이름")
    p.add_argument("--write-final", action="store_true", help="모두 통과하면 final.md 생성")
    p.set_defaults(handler=cmd_count)

    p = sub.add_parser("clean", help="근거 주석 제거와 줄바꿈 정리")
    p.add_argument("input")
    p.add_argument("--out", required=True)
    p.set_defaults(handler=cmd_clean)

    p = sub.add_parser("init-data", help="데이터 저장소 뼈대 생성 (기존 파일은 건너뜀)")
    p.add_argument("target")
    p.set_defaults(handler=cmd_init_data)

    p = sub.add_parser("dart", help="DART 사업보고서의 사업의 내용과 재무 요약")
    p.add_argument("name", help="회사명")
    p.add_argument("--corp-code", help="후보가 여러 개일 때 고른 고유번호")
    p.set_defaults(handler=cmd_dart)

    p = sub.add_parser("news", help="최근 뉴스 검색 (네이버)")
    p.add_argument("query", help="검색어 (예: 회사명, \"회사명 AI\")")
    p.add_argument("--months", type=int, default=6)
    p.set_defaults(handler=cmd_news)
    p = sub.add_parser("search", help="사람인·고용24 공고 검색, _inbox에 저장")
    p.add_argument("keywords", nargs="+")
    p.add_argument("--since", type=days, help="최근 N일 (예: 7d)")
    p.set_defaults(handler=cmd_search)

    p = sub.add_parser("company", help="기업 규모 정보 (DART, 국민연금), 90일 캐시")
    p.add_argument("name")
    p.add_argument("--corp-code", help="DART 후보 중 고른 고유번호")
    p.add_argument("--nps-seq", help="국민연금 사업장 후보 중 고른 seq")
    p.set_defaults(handler=cmd_company)

    p = sub.add_parser("filter", help="preferences.yaml 필수 조건으로 _inbox 공고 거르기")
    p.add_argument("inbox", help="_inbox 파일 경로 또는 이름 (예: 2026-10-13.json)")
    p.set_defaults(handler=cmd_filter)

    p = sub.add_parser("fetch", help="공고 페이지 한 건의 본문 텍스트 읽기")
    p.add_argument("url")
    p.add_argument("--interactive", action="store_true",
                   help="보이는 브라우저로 열고, 창을 닫으면 닫기 직전 화면을 읽음")
    p.add_argument("--save-html", help="페이지 HTML을 이 경로에 저장 (파서 fixture용)")
    p.set_defaults(handler=cmd_fetch)

    # 개인 환경 전용 확장(career_ai/extensions/*.py). 모듈이 없으면 명령도 없다.
    for module in pkgutil.iter_modules(extensions.__path__):
        extension = importlib.import_module(f"{extensions.__name__}.{module.name}")
        if hasattr(extension, "register"):
            extension.register(sub)

    notion = sub.add_parser("notion", help="Notion 지원 현황 연동")
    notion_sub = notion.add_subparsers(dest="notion_command", required=True)
    p = notion_sub.add_parser("init", help="'지원 현황' 데이터베이스 만들기")
    p.add_argument("--parent", required=True, help="데이터베이스를 넣을 Notion 페이지 URL 또는 ID")
    p.set_defaults(handler=cmd_notion_init)
    p = notion_sub.add_parser("push", help="지원 폴더를 Notion 페이지로 저장")
    p.add_argument("app_dir", help="지원 폴더 경로 또는 applications/ 아래 폴더 이름")
    p.set_defaults(handler=cmd_notion_push)

    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows 콘솔 기본 인코딩(cp949)으로는 이모지 등을 출력할 수 없다.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 1
    try:
        return args.handler(args)
    except Exception as e:  # noqa: BLE001 — Claude가 읽을 수 있게 traceback 대신 JSON으로 알린다
        return fail("internal", f"{type(e).__name__}: {e}")
