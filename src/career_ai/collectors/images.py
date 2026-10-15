"""공고 이미지 내려받기와 자르기.

채용 공고 상세는 세로로 아주 긴 이미지 한 장인 경우가 많아(예: 1875×13738),
Claude가 읽을 수 있도록 폭을 줄이고 위에서부터 여러 조각으로 잘라 PNG로 저장한다.
"""

import io
from pathlib import Path

import httpx
from PIL import Image

MAX_WIDTH = 1200
SLICE_HEIGHT = 1600


def slice_image(data: bytes, out_dir: Path, stem: str) -> list[Path]:
    image = Image.open(io.BytesIO(data)).convert("RGB")
    if image.width > MAX_WIDTH:
        height = round(image.height * MAX_WIDTH / image.width)
        image = image.resize((MAX_WIDTH, height), Image.LANCZOS)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for n, top in enumerate(range(0, image.height, SLICE_HEIGHT), start=1):
        piece = image.crop((0, top, image.width, min(top + SLICE_HEIGHT, image.height)))
        path = out_dir / f"{stem}-{n:02d}.png"
        piece.save(path, "PNG")
        files.append(path)
    return files


def download_and_slice(client: httpx.Client, urls: list[str], out_dir: Path) -> dict:
    """이미지마다 내려받아 자른다. 실패한 주소는 failed에 모으고 나머지는 계속한다."""
    files, failed = [], []
    for n, url in enumerate(urls, start=1):
        try:
            response = client.get(url, follow_redirects=True, timeout=60)
            response.raise_for_status()
            files += slice_image(response.content, out_dir, f"posting-{n}")
        except (httpx.HTTPError, OSError):  # OSError: Pillow가 이미지를 못 읽을 때
            failed.append(url)
    return {"files": files, "failed": failed}
