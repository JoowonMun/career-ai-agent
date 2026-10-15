"""설정 로드. .env는 저장소 루트에서 찾고, 상대 경로는 저장소 루트 기준으로 해석한다."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(Exception):
    """설정이 없거나 잘못됐을 때. 메시지는 사용자에게 그대로 보여 준다."""


@dataclass(frozen=True)
class Config:
    data_dir: Path


def load_config(repo_root: Path = REPO_ROOT) -> Config:
    load_dotenv(repo_root / ".env", override=False)
    raw = os.environ.get("CAREER_DATA_DIR")
    if not raw:
        raise ConfigError(
            "CAREER_DATA_DIR가 설정되지 않았습니다. "
            ".env.example을 복사해 .env를 만들고 데이터 폴더 경로를 적어 주세요."
        )
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = repo_root / path
    path = path.resolve()
    if not path.is_dir():
        raise ConfigError(
            f"CAREER_DATA_DIR 폴더가 없습니다: {path}. "
            f"`uv run career-ai init-data {raw}`로 만들 수 있습니다."
        )
    return Config(data_dir=path)


def api_keys(names: tuple[str, ...], repo_root: Path = REPO_ROOT) -> tuple[str, ...]:
    """외부 API 키를 .env에서 읽는다. 하나라도 비어 있으면 빠진 키 이름을 모두 알려 준다."""
    load_dotenv(repo_root / ".env", override=False)
    values = tuple(os.environ.get(name, "") for name in names)
    missing = [name for name, value in zip(names, values, strict=True) if not value]
    if missing:
        raise ConfigError(
            f"{', '.join(missing)}가 설정되지 않았습니다. "
            ".env에 값을 적어 주세요. 발급 방법은 README의 'API 키' 절에 있습니다."
        )
    return values


def require_setting(name: str, hint: str, repo_root: Path = REPO_ROOT) -> str:
    load_dotenv(repo_root / ".env", override=False)
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name}가 설정되지 않았습니다. {hint}")
    return value


def optional_keys(names: tuple[str, ...], repo_root: Path = REPO_ROOT) -> dict[str, str]:
    """없어도 되는 키. 있는 것만 돌려준다(없는 수집원은 건너뛴다)."""
    load_dotenv(repo_root / ".env", override=False)
    return {name: os.environ[name] for name in names if os.environ.get(name)}
