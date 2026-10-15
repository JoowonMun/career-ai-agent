"""데이터 저장소 뼈대 생성. 이미 있는 파일은 절대 덮어쓰지 않는다."""

import shutil
from pathlib import Path

from career_ai.config import REPO_ROOT

TEMPLATE_DIR = REPO_ROOT / "examples" / "data-template"


def init_data(target: Path, template: Path = TEMPLATE_DIR) -> dict:
    created, skipped = [], []
    for src in sorted(template.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(template)
        dst = target / rel
        if dst.exists():
            skipped.append(rel.as_posix())
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        created.append(rel.as_posix())
    return {"target": str(target.resolve()), "created": created, "skipped": skipped}
