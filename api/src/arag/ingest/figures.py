"""図の説明（specs/003-ingestion/design.md §3.5、R19）。

画像はベクトル化しない。視覚対応モデルが設定されているときだけ、図の日本語説明を
`figure` 種別の子チャンクとして所属セクションに追加する。
"""

import base64
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.items.picture.picture import PictureItem
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from arag.ingest.chunking import ChunkDraft, SectionDraft
from arag.ingest.contextualize import Usage
from arag.logging import get_logger
from arag.prompts import load_prompt

log = get_logger("arag.ingest.figures")

MIN_AREA_RATIO = 0.05
_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}


class FigureDescriber(Protocol):
    async def describe(
        self, image: bytes, mime: str, caption: str, context: str
    ) -> tuple[str, AIMessage | None]: ...


class LlmFigureDescriber:
    def __init__(self, model: BaseChatModel) -> None:
        self.model = model
        self.system = load_prompt("describe_figure")

    async def describe(
        self, image: bytes, mime: str, caption: str, context: str
    ) -> tuple[str, AIMessage | None]:
        msg = await self.model.ainvoke(
            [
                SystemMessage(self.system),
                HumanMessage(
                    content=[
                        {"type": "image", "base64": base64.b64encode(image).decode(), "mime_type": mime},
                        {
                            "type": "text",
                            "text": f"<context>\nキャプション: {caption}\n{context}\n</context>",
                        },
                    ]
                ),
            ]
        )
        assert isinstance(msg, AIMessage)
        text = (
            msg.content
            if isinstance(msg.content, str)
            else "".join(b.get("text", "") for b in msg.content if isinstance(b, dict))
        )
        return text.strip(), msg


@dataclass(slots=True)
class FigureCandidate:
    index: int  # 1 始まり（assets/fig-{index}.*）
    asset: str
    page: int | None
    caption: str


def _area_ratio(doc: DoclingDocument, pic: PictureItem) -> float:
    if not pic.prov:
        return 1.0  # 位置が分からない画像（DOCX 等）は除外しない
    p = pic.prov[0]
    page = doc.pages.get(p.page_no)
    if page is None or not page.size.width or not page.size.height:
        return 1.0
    return float(abs(p.bbox.width * p.bbox.height) / (page.size.width * page.size.height))


def figure_candidates(
    doc: DoclingDocument, assets: dict[str, bytes], min_area_ratio: float = MIN_AREA_RATIO
) -> list[FigureCandidate]:
    by_index = {name.split(".")[0].removeprefix("fig-"): name for name in assets if name.startswith("fig-")}
    out: list[FigureCandidate] = []
    for n, pic in enumerate(doc.pictures, start=1):
        asset = by_index.get(str(n))
        if asset is None or _area_ratio(doc, pic) < min_area_ratio:
            continue
        out.append(
            FigureCandidate(
                index=n,
                asset=asset,
                page=pic.prov[0].page_no if pic.prov else None,
                caption=pic.caption_text(doc).strip(),
            )
        )
    return out


def _section_for(page: int | None, sections: Sequence[SectionDraft]) -> SectionDraft | None:
    if not sections:
        return None
    if page is not None:
        for s in sections:
            if s.page_start is not None and s.page_end is not None and s.page_start <= page <= s.page_end:
                return s
    return sections[0]


async def describe_figures(
    doc: DoclingDocument,
    assets: dict[str, bytes],
    sections: Sequence[SectionDraft],
    chunks: Sequence[ChunkDraft],
    describer: FigureDescriber | None,
    count_tokens: Callable[[str], int] = len,
    usage: Usage | None = None,
) -> list[ChunkDraft]:
    """図チャンクを返す（ordinal は呼び出し側で振り直す）。無効なら空。"""
    if describer is None:
        return []
    out: list[ChunkDraft] = []
    for fig in figure_candidates(doc, assets):
        sec = _section_for(fig.page, sections)
        if sec is None:
            continue
        nearby = [c.text for c in chunks if c.section_ordinal == sec.ordinal][:3]
        ext = fig.asset.rsplit(".", 1)[-1].lower()
        try:
            text, msg = await describer.describe(
                assets[fig.asset], _MIME.get(ext, "image/png"), fig.caption, "\n".join(nearby)[:2000]
            )
            if usage is not None and msg is not None:
                usage.add(msg)
        except Exception as e:  # 失敗した図はキャプションと本文だけに任せる（R19）
            log.warning("describe_figure_failed", figure=fig.index, error=f"{type(e).__name__}: {e}")
            if usage is not None:
                usage.failures += 1
            continue
        if not text:
            continue
        body = f"図: {fig.caption}\n{text}" if fig.caption else f"図: {text}"
        out.append(
            ChunkDraft(
                ordinal=-1,
                section_ordinal=sec.ordinal,
                block_type="figure",
                heading_path=sec.heading_path,
                page_start=fig.page,
                page_end=fig.page,
                text=body,
                token_len=count_tokens(body),
                boxes=[],
            )
        )
    return out
