"""質問に添える画像の検証・縮小（specs/017-query-image A1）。"""

import base64
import io

import pytest
from PIL import Image

from arag.agent.query_image import ImageRejected, decode_query_image


def _b64(fmt: str, size: tuple[int, int] = (40, 30), mode: str = "RGB", **save: object) -> str:
    buf = io.BytesIO()
    Image.new(mode, size, (200, 30, 30) if mode == "RGB" else (200, 30, 30, 120)).save(buf, fmt, **save)
    return base64.b64encode(buf.getvalue()).decode()


@pytest.mark.parametrize("fmt,mode", [("PNG", "RGBA"), ("JPEG", "RGB"), ("WEBP", "RGB"), ("GIF", "RGB")])
def test_converts_to_jpeg(fmt: str, mode: str) -> None:
    img = decode_query_image(_b64(fmt, mode=mode), max_px=1280, max_bytes=1_000_000)
    assert img.data[:3] == b"\xff\xd8\xff"  # JPEG
    assert (img.width, img.height) == (40, 30)


def test_shrinks_long_side() -> None:
    img = decode_query_image(_b64("PNG", size=(3000, 1500)), max_px=1280, max_bytes=10_000_000)
    assert (img.width, img.height) == (1280, 640)
    assert Image.open(io.BytesIO(img.data)).size == (1280, 640)


def test_strips_metadata() -> None:
    exif = Image.Exif()
    exif[0x010F] = "SecretCam"  # Make
    img = decode_query_image(_b64("JPEG", exif=exif.tobytes()), max_px=1280, max_bytes=1_000_000)
    assert b"SecretCam" not in img.data


def test_accepts_data_url_prefix() -> None:
    img = decode_query_image("data:image/png;base64," + _b64("PNG"), max_px=1280, max_bytes=1_000_000)
    assert img.width == 40


@pytest.mark.parametrize(
    "data,match",
    [
        ("not base64!!", "読み込めません"),
        (base64.b64encode(b"hello world").decode(), "画像ではありません"),
        (base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40).decode(), "画像ではありません"),
    ],
)
def test_rejects_bad_input(data: str, match: str) -> None:
    with pytest.raises(ImageRejected, match=match):
        decode_query_image(data, max_px=1280, max_bytes=1_000_000)


def test_rejects_too_large() -> None:
    with pytest.raises(ImageRejected, match="大きすぎます"):
        decode_query_image(_b64("PNG", size=(400, 400)), max_px=1280, max_bytes=100)


def test_rejects_other_formats() -> None:
    with pytest.raises(ImageRejected, match="形式"):
        decode_query_image(_b64("BMP"), max_px=1280, max_bytes=1_000_000)
