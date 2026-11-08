"""文脈付与（Contextual Retrieval。specs/003-ingestion/design.md §3.3、R20・R21）。

子チャンクごとに「この塊は〈文書名〉の〈章〉で〜を述べている」という 1〜2 文を作る。
失敗した子チャンクだけ見出しパスによる文脈にし、入庫自体は止めない。
"""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from arag.ingest.chunking import HEADING_SEP, ChunkDraft, SectionDraft
from arag.logging import get_logger
from arag.prompts import load_prompt

log = get_logger("arag.ingest.contextualize")

ContextSource = Literal["llm", "heading"]
ProgressFn = Callable[[int, int], Awaitable[None]]
_MAX_CONTEXT_CHARS = 400


@dataclass(slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    calls: int = 0
    failures: int = 0

    def add(self, msg: AIMessage) -> None:
        self.calls += 1
        um = msg.usage_metadata
        if not um:
            return
        self.input_tokens += um.get("input_tokens", 0)
        self.output_tokens += um.get("output_tokens", 0)
        details = um.get("input_token_details") or {}
        self.cache_read_tokens += details.get("cache_read", 0)
        self.cache_creation_tokens += details.get("cache_creation", 0)

    def as_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "calls": self.calls,
            "failures": self.failures,
        }


@dataclass(slots=True)
class ContextResult:
    contexts: list[str]
    sources: list[ContextSource]
    usage: Usage = field(default_factory=Usage)
    model: str | None = None


class Contextualizer(Protocol):
    async def contextualize(
        self,
        title: str,
        sections: Sequence[SectionDraft],
        chunks: Sequence[ChunkDraft],
        on_progress: ProgressFn | None = None,
    ) -> ContextResult: ...


def heading_context(title: str, chunk: ChunkDraft) -> str:
    return HEADING_SEP.join(p for p in (title, chunk.heading_path) if p)


class HeadingContextualizer:
    """LLM を使わないフォールバック: 「文書名 > 見出しパス」。"""

    async def contextualize(
        self,
        title: str,
        sections: Sequence[SectionDraft],
        chunks: Sequence[ChunkDraft],
        on_progress: ProgressFn | None = None,
    ) -> ContextResult:
        if on_progress:
            await on_progress(len(chunks), len(chunks))
        return ContextResult(
            contexts=[heading_context(title, c) for c in chunks], sources=["heading"] * len(chunks)
        )


def _clean(text: str) -> str:
    text = " ".join(text.split()).strip("「」\"' ")
    return text[:_MAX_CONTEXT_CHARS]


def _content_text(msg: AIMessage) -> str:
    if isinstance(msg.content, str):
        return msg.content
    return "".join(b.get("text", "") for b in msg.content if isinstance(b, dict))


class LlmContextualizer:
    def __init__(
        self,
        model: BaseChatModel,
        *,
        model_name: str,
        concurrency: int = 8,
        max_document_tokens: int = 60_000,
        neighbor_sections: int = 2,
        count_tokens: Callable[[str], int] = len,
        use_cache_control: bool | None = None,
    ) -> None:
        self.model = model
        self.model_name = model_name
        self.concurrency = max(1, concurrency)
        self.max_document_tokens = max_document_tokens
        self.neighbor_sections = neighbor_sections
        self.count_tokens = count_tokens
        # Anthropic は明示の cache_control が要る。OpenAI 系は前方一致で自動キャッシュ。
        self.use_cache_control = (
            "anthropic" in type(model).__name__.lower() if use_cache_control is None else use_cache_control
        )
        self.system = load_prompt("contextualize")

    def _document_text(self, title: str, sections: Sequence[SectionDraft], center: int | None) -> str:
        """全文が上限内なら全文（全子チャンクで同じ＝キャッシュが効く）。超えたら該当 ±2 セクション。"""
        if center is None:
            picked = list(sections)
        else:
            picked = [s for s in sections if abs(s.ordinal - center) <= self.neighbor_sections]
        body = "\n\n".join(f"## {s.heading_path}\n{s.text}" if s.heading_path else s.text for s in picked)
        return f'<document title="{title}">\n{body}\n</document>'

    def _messages(self, document: str, chunk: ChunkDraft) -> list[Any]:
        doc_block: dict[str, Any] = {"type": "text", "text": document}
        if self.use_cache_control:
            doc_block["cache_control"] = {"type": "ephemeral"}
        chunk_block = {"type": "text", "text": f"<chunk>\n{chunk.text}\n</chunk>"}
        return [SystemMessage(self.system), HumanMessage(content=[doc_block, chunk_block])]

    async def contextualize(
        self,
        title: str,
        sections: Sequence[SectionDraft],
        chunks: Sequence[ChunkDraft],
        on_progress: ProgressFn | None = None,
    ) -> ContextResult:
        total_tokens = sum(s.token_len for s in sections)
        whole = total_tokens <= self.max_document_tokens
        full_doc = self._document_text(title, sections, None) if whole else ""
        result = ContextResult(
            contexts=[heading_context(title, c) for c in chunks],
            sources=["heading"] * len(chunks),
            model=self.model_name,
        )
        done = 0
        sem = asyncio.Semaphore(self.concurrency)

        async def one(i: int) -> None:
            nonlocal done
            chunk = chunks[i]
            document = full_doc or self._document_text(title, sections, chunk.section_ordinal)
            async with sem:
                try:
                    msg = await self.model.ainvoke(self._messages(document, chunk))
                    assert isinstance(msg, AIMessage)
                    result.usage.add(msg)
                    text = _clean(_content_text(msg))
                    if text:
                        result.contexts[i] = text
                        result.sources[i] = "llm"
                    else:
                        result.usage.failures += 1
                except Exception as e:  # 1 件の失敗で入庫を止めない（R20）
                    result.usage.failures += 1
                    log.warning(
                        "contextualize_failed", ordinal=chunk.ordinal, error=f"{type(e).__name__}: {e}"
                    )
            done += 1
            if on_progress:
                await on_progress(done, len(chunks))

        if chunks:
            # 最初の 1 件を単独で送ってキャッシュを作ってから残りを並列に（R21）
            await one(0)
            await asyncio.gather(*(one(i) for i in range(1, len(chunks))))
        return result
