"""質問に添える画像（specs/017-query-image）。

受け付けた画像は長辺を縮め、RGB の JPEG に変換して保存する（メタデータは残さない）。
回答の前に図の説明用モデルで文章にし、質問に添えてエージェントへ渡す（方式 A）。
"""

import base64
import binascii
import io
import re
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from PIL import Image, ImageOps, UnidentifiedImageError

from arag.prompts import load_prompt

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
JPEG_QUALITY = 85
DEFAULT_QUERY = "この画像について関連資料を調べてください"
_DATA_URL = re.compile(r"^data:[\w/+.-]+;base64,")


class ImageRejected(ValueError):
    """利用者に見せる理由つきで画像を断る。"""


@dataclass(frozen=True, slots=True)
class QueryImage:
    data: bytes  # JPEG
    width: int
    height: int


def decode_query_image(b64: str, *, max_px: int, max_bytes: int) -> QueryImage:
    """base64（data URL も可）を検証し、長辺 max_px 以内の JPEG にする。"""
    try:
        raw = base64.b64decode(_DATA_URL.sub("", b64.strip()), validate=True)
    except (binascii.Error, ValueError) as e:
        raise ImageRejected("画像を読み込めませんでした") from e
    if len(raw) > max_bytes:
        raise ImageRejected(f"画像が大きすぎます（{max_bytes // 1_000_000}MB まで）")
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt = probe.format
            probe.verify()
        if fmt not in ALLOWED_FORMATS:
            raise ImageRejected("対応していない形式です（JPEG・PNG・WebP・GIF）")
        with Image.open(io.BytesIO(raw)) as src:
            src.seek(0)  # GIF は最初のフレーム
            im = ImageOps.exif_transpose(src)
            im.thumbnail((max_px, max_px))
            rgb = _to_rgb(im)
    except ImageRejected:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as e:
        raise ImageRejected("画像ではありません（または壊れています）") from e
    out = io.BytesIO()
    rgb.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return QueryImage(data=out.getvalue(), width=rgb.width, height=rgb.height)


def _to_rgb(im: Image.Image) -> Image.Image:
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.getchannel("A"))
        return bg
    return im.convert("RGB")


def image_key(user_id: str, image_id: str) -> str:
    return f"queries/{user_id}/{image_id}.jpg"


class QueryImageReader:
    """質問を踏まえて画像の内容を書き出す（図の説明用モデル）。"""

    def __init__(self, model: BaseChatModel) -> None:
        self.model = model
        self.system = load_prompt("read_query_image")

    async def read(self, image: bytes, question: str) -> str:
        msg = await self.model.ainvoke(
            [
                SystemMessage(self.system),
                HumanMessage(
                    content=[
                        {
                            "type": "image",
                            "base64": base64.b64encode(image).decode(),
                            "mime_type": "image/jpeg",
                        },
                        {"type": "text", "text": f"<question>\n{question}\n</question>"},
                    ]
                ),
            ]
        )
        assert isinstance(msg, AIMessage)
        return msg.text.strip()


def with_image_description(query: str, description: str | None) -> str:
    """エージェントに渡す質問文。読み取れなかったときはその旨を添える。"""
    if description is None:
        return f"{query}\n\n（添付画像は読み取れませんでした）"
    return f"{query}\n\n<image_description>\n{description}\n</image_description>"
