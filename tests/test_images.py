import io

import httpx
from PIL import Image

from career_ai.collectors import images


def png_bytes(width, height, fmt="PNG"):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, fmt)
    return buffer.getvalue()


def test_tall_image_is_resized_and_sliced(tmp_path):
    files = images.slice_image(png_bytes(1875, 13738), tmp_path, "posting-1")
    sizes = [Image.open(f).size for f in files]
    assert all(w == images.MAX_WIDTH for w, _ in sizes)
    assert all(h <= images.SLICE_HEIGHT for _, h in sizes)
    total = sum(h for _, h in sizes)
    assert abs(total - round(13738 * images.MAX_WIDTH / 1875)) <= len(sizes)
    assert [f.name for f in files][:2] == ["posting-1-01.png", "posting-1-02.png"]


def test_small_image_is_kept_as_one_piece(tmp_path):
    files = images.slice_image(png_bytes(900, 1200, "WEBP"), tmp_path, "posting-1")
    assert len(files) == 1 and Image.open(files[0]).size == (900, 1200)


def test_download_and_slice_skips_failed_urls(tmp_path):
    def handler(request):
        if "bad" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(200, content=png_bytes(800, 500))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = images.download_and_slice(
            client, ["https://cdn.test/a.webp", "https://cdn.test/bad.webp"], tmp_path)
    assert [f.name for f in result["files"]] == ["posting-1-01.png"]
    assert result["failed"] == ["https://cdn.test/bad.webp"]
