"""エージェントのテスト用の偽物（モデル・検索・セッション）。"""

import json
import uuid
from collections.abc import Iterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from pydantic import Field

from arag.search.schemas import SearchHit, SearchRequest, SearchResult, SearchTrace


class FakeToolModel(GenericFakeChatModel):
    """決めた順に AIMessage を返す。受け取った messages と bind された tools を記録する。"""

    calls: list[list[BaseMessage]] = Field(default_factory=list)
    tool_counts: list[int] = Field(default_factory=list)
    tool_choices: list[Any] = Field(default_factory=list)
    bound: int = 0
    choice: Any = None

    def bind_tools(self, tools: Sequence[Any], **kw: Any) -> Any:  # type: ignore[override]
        self.bound = len(tools)
        self.choice = kw.get("tool_choice")
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls.append(list(messages))
        self.tool_counts.append(self.bound)
        self.tool_choices.append(self.choice)
        self.bound = 0
        return super()._generate(messages, stop, run_manager, **kwargs)

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        msg = self._generate(messages, stop, run_manager, **kwargs).generations[0].message
        assert isinstance(msg, AIMessage)
        text = msg.text
        # 本文は 2 つに分けて流す（差分の扱いを確かめるため）
        pieces = [text[: len(text) // 2], text[len(text) // 2 :]] if text else [""]
        for i, piece in enumerate(pieces):
            last = i == len(pieces) - 1
            chunk = AIMessageChunk(
                content=piece,
                id=msg.id,
                tool_call_chunks=[
                    {"name": tc["name"], "args": json.dumps(tc["args"]), "id": tc["id"], "index": j}
                    for j, tc in enumerate(msg.tool_calls)
                ]
                if last
                else [],
                usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15} if last else None,
                chunk_position="last" if last else None,
            )
            yield ChatGenerationChunk(message=chunk)


def script(*msgs: AIMessage) -> Iterator[AIMessage]:
    return iter(msgs)


def tool_call(name: str, **args: Any) -> AIMessage:
    return AIMessage(
        content="", tool_calls=[{"name": name, "args": args, "id": f"call_{uuid.uuid4().hex[:8]}"}]
    )


DOC = uuid.uuid4()


def fake_hit(text: str, score: float = 0.9) -> SearchHit:
    return SearchHit(
        rank=1,
        chunk_id=uuid.uuid4(),
        document_id=DOC,
        document_name="規程.pdf",
        kb_id=uuid.uuid4(),
        section_id=uuid.uuid4(),
        heading_path="第1章",
        page_start=2,
        page_end=2,
        block_type="text",
        text=text,
        context="",
        boxes=[],
        score=score,
        fused_score=0.1,
    )


class FakeSearch:
    def __init__(self, *texts: str) -> None:
        self.hits = [fake_hit(t) for t in texts]
        self.requests: list[SearchRequest] = []

    async def __call__(self, _s: Any, _p: Any, req: SearchRequest) -> SearchResult:
        self.requests.append(req)
        return SearchResult(hits=self.hits, trace=SearchTrace())


@asynccontextmanager
async def _null_session() -> Any:
    yield None


def null_sessionmaker() -> Any:
    return _null_session()


class StatusError(Exception):
    """openai の APIStatusError に似せた例外（status_code を持つ）。"""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"Error code: {status_code}")
        self.status_code = status_code


class FailingModel(FakeToolModel):
    """呼ばれるたびに決めた例外を投げる（呼ばれた回数を数える）。"""

    error: Any = None
    failures: int = 0

    def _generate(self, *a: Any, **kw: Any) -> ChatResult:
        self.failures += 1
        raise self.error
