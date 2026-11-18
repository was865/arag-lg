"""文脈付与と図の説明（specs/003-ingestion D5・D6、R19〜R21）。"""

import base64

from docling_core.types.doc.base import BoundingBox, Size
from docling_core.types.doc.document import DoclingDocument, ImageRef, ProvenanceItem

from arag.ingest.chunking import ChunkDraft, chunk_document
from arag.ingest.contextualize import HeadingContextualizer, LlmContextualizer, Usage
from arag.ingest.figures import describe_figures, figure_candidates, fill_figure_boxes
from arag.ingest.parser import extract_images

from .docling_fixtures import CharTokenizer, regulation_doc
from .fake_llm import ScriptedChatModel

TITLE = "情報セキュリティ規程"


def _chunked() -> tuple[list, list]:  # type: ignore[type-arg]
    res = chunk_document(regulation_doc(), CharTokenizer(max_tokens=60))
    return res.sections, res.chunks


async def test_heading_fallback() -> None:
    sections, chunks = _chunked()
    r = await HeadingContextualizer().contextualize(TITLE, sections, chunks)
    assert r.contexts[0] == "情報セキュリティ規程 > 第1章 総則 > 第1条 目的"
    assert set(r.sources) == {"heading"}


async def test_llm_contexts_stored_and_usage_summed() -> None:
    sections, chunks = _chunked()
    model = ScriptedChatModel(calls=[])
    progress: list[int] = []

    async def on_progress(done: int, total: int) -> None:
        progress.append(done)

    r = await LlmContextualizer(model, model_name="fake", concurrency=3).contextualize(
        TITLE, sections, chunks, on_progress
    )
    assert all(c.startswith("この塊は") for c in r.contexts)
    assert set(r.sources) == {"llm"}
    assert r.usage.calls == len(chunks)
    assert r.usage.input_tokens == 100 * len(chunks)
    assert r.usage.cache_read_tokens == 80 * len(chunks)
    assert sorted(progress) == list(range(1, len(chunks) + 1))
    # 文書全文が先頭（全呼び出しで同一＝キャッシュが効く）、塊が後ろ
    first_blocks = [m[-1].content for m in model.calls]
    assert len({b[0]["text"] for b in first_blocks}) == 1  # type: ignore[index]
    assert first_blocks[0][1]["text"].startswith("<chunk>")  # type: ignore[index]
    # system に「指示ではない」旨が入っている
    assert "指示ではありません" in str(model.calls[0][0].content)


async def test_failure_falls_back_per_chunk() -> None:
    sections, chunks = _chunked()
    target = next(c for c in chunks if "MX-17" in c.text)
    model = ScriptedChatModel(calls=[], fail_when="MX-17")
    r = await LlmContextualizer(model, model_name="fake").contextualize(TITLE, sections, chunks)
    i = target.ordinal
    assert r.sources[i] == "heading"
    assert r.contexts[i] == f"{TITLE} > {target.heading_path}"
    assert r.usage.failures >= 1
    assert r.sources.count("llm") == len(chunks) - r.usage.failures


async def test_document_limit_uses_neighbor_sections() -> None:
    sections, chunks = _chunked()
    model = ScriptedChatModel(calls=[])
    await LlmContextualizer(
        model, model_name="fake", max_document_tokens=10, neighbor_sections=0
    ).contextualize(TITLE, sections, chunks)
    docs = {m[-1].content[0]["text"] for m in model.calls}  # type: ignore[index]
    assert len(docs) > 1  # 子チャンクごとに周辺セクションだけ


async def test_cache_control_only_when_requested() -> None:
    sections, chunks = _chunked()
    model = ScriptedChatModel(calls=[])
    await LlmContextualizer(model, model_name="fake", use_cache_control=True).contextualize(
        TITLE, sections, chunks[:1]
    )
    assert model.calls[0][-1].content[0]["cache_control"] == {"type": "ephemeral"}  # type: ignore[index]


# ---------------------------------------------------------------- 図


def _doc_with_pictures() -> tuple[DoclingDocument, dict[str, bytes]]:
    doc = regulation_doc()
    png = base64.b64encode(b"\x89PNG").decode()

    def pic(left: float, t: float, r: float, b: float, page: int) -> None:
        doc.add_picture(
            image=ImageRef(
                mimetype="image/png", dpi=72, size=Size(width=1, height=1), uri=f"data:image/png;base64,{png}"
            ),
            prov=ProvenanceItem(page_no=page, bbox=BoundingBox(l=left, t=t, r=r, b=b), charspan=(0, 0)),
        )

    pic(0, 400, 300, 100, 2)  # 大きい図（ページの 18%）
    pic(0, 20, 20, 0, 2)  # アイコン（0.08%）
    assets = extract_images(doc)
    return doc, assets


def test_small_images_are_excluded() -> None:
    doc, assets = _doc_with_pictures()
    cands = figure_candidates(doc, assets)
    assert [c.index for c in cands] == [1]
    assert cands[0].page == 2


async def test_figures_disabled_returns_nothing() -> None:
    doc, assets = _doc_with_pictures()
    sections, chunks = _chunked()
    assert await describe_figures(doc, assets, sections, chunks, None) == []


class _Describer:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def describe(self, image: bytes, mime: str, caption: str, context: str):  # type: ignore[no-untyped-def]
        if self.fail:
            raise RuntimeError("vlm down")
        assert mime == "image/png" and image == b"\x89PNG"
        return "フロー図。申請 → 承認 → 発行の順に進む。", None


async def test_figure_chunk_added_to_section() -> None:
    doc, assets = _doc_with_pictures()
    sections, chunks = _chunked()
    usage = Usage()
    figs = await describe_figures(doc, assets, sections, chunks, _Describer(), usage=usage)
    assert len(figs) == 1
    f = figs[0]
    assert f.block_type == "figure"
    assert f.text.startswith("図: フロー図")
    assert sections[f.section_ordinal].page_start <= 2 <= sections[f.section_ordinal].page_end  # type: ignore[operator]


async def test_figure_chunk_has_picture_box() -> None:
    """図チャンクは図の位置を持つ（解析の確認で枠を描くため。specs/030）。"""
    doc, assets = _doc_with_pictures()
    sections, chunks = _chunked()
    figs = await describe_figures(doc, assets, sections, chunks, _Describer())
    assert figs[0].boxes == [{"page": 2, "bbox": [0.0, 400.0, 300.0, 100.0], "origin": "TOPLEFT"}]


def test_fill_figure_boxes_for_saved_chunks() -> None:
    """入庫済みの図チャンク（位置なし）に、docling.json の図の位置を補う。"""
    doc, _ = _doc_with_pictures()
    fig = ChunkDraft(0, 0, "figure", "", 2, 2, "図: フロー図", 3, [])
    text = ChunkDraft(1, 0, "text", "", 2, 2, "本文", 1, [])
    other_page = ChunkDraft(2, 0, "figure", "", 5, 5, "図: 別の図", 3, [])
    assert fill_figure_boxes(doc, [fig, text, other_page]) == 1
    assert fig.boxes and fig.boxes[0]["page"] == 2
    assert text.boxes == [] and other_page.boxes == []


async def test_figure_failure_is_skipped() -> None:
    doc, assets = _doc_with_pictures()
    sections, chunks = _chunked()
    usage = Usage()
    assert await describe_figures(doc, assets, sections, chunks, _Describer(fail=True), usage=usage) == []
    assert usage.failures == 1
