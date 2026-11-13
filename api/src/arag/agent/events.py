"""run のイベント（SSE の契約。specs/005-agent R10）。OpenAPI に出して TS 型を生成する。"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from arag.agent.steps import Step

NoAnswerReason = Literal[
    "no_sources",
    "no_relevant_sources",
    "step_budget_exhausted",
    "tool_failed",
    "generation_failed",
    "empty_generation",
]


class CitationRef(BaseModel):
    source_id: str
    section_id: str


class SourceSection(BaseModel):
    id: str
    n: int
    heading: str
    body: str
    block_type: str
    page: int | None = None


class SourceView(BaseModel):
    id: str
    title: str
    sections: list[SourceSection]
    score: float | None = None


class RunStarted(BaseModel):
    type: Literal["run.started"] = "run.started"
    run_id: str
    thread_id: str
    message_id: str
    model_id: str


class StepEvent(BaseModel):
    type: Literal["step"] = "step"
    step: Step


class AnswerDelta(BaseModel):
    type: Literal["answer.delta"] = "answer.delta"
    text: str


class AnswerReset(BaseModel):
    type: Literal["answer.reset"] = "answer.reset"


class SourcesEvent(BaseModel):
    type: Literal["sources"] = "sources"
    citation_map: dict[str, CitationRef]
    sources: list[SourceView]


class RunCompleted(BaseModel):
    type: Literal["run.completed"] = "run.completed"
    message_id: str
    answer: str
    tokens_in: int
    tokens_out: int
    duration_ms: int
    no_answer_reason: NoAnswerReason | None = None
    citation_map: dict[str, CitationRef]
    sources: list[SourceView]
    # 続けて聞く質問の候補。完了の後に `followups` で届ける（specs/028 T24）ので、ここは空
    suggestions: list[str] = []
    # true なら、この後に `followups` が届く（ストリームはそこで閉じる）。false ならここで閉じる
    followups_pending: bool = False


class FollowupsEvent(BaseModel):
    """続けて聞く質問の候補（specs/028 T24）。run.completed の後に届き、ストリームはここで閉じる。"""

    type: Literal["followups"] = "followups"
    message_id: str
    suggestions: list[str] = []


class RunFailed(BaseModel):
    type: Literal["run.failed"] = "run.failed"
    code: str
    message: str


class RunCancelled(BaseModel):
    type: Literal["run.cancelled"] = "run.cancelled"
    message_id: str


RunEvent = Annotated[
    RunStarted
    | StepEvent
    | AnswerDelta
    | AnswerReset
    | SourcesEvent
    | RunCompleted
    | FollowupsEvent
    | RunFailed
    | RunCancelled,
    Field(discriminator="type"),
]
RUN_EVENT = TypeAdapter(RunEvent)
TERMINAL = frozenset({"run.completed", "run.failed", "run.cancelled"})


def closes_stream(typ: str, ev: dict[str, Any]) -> bool:
    """このイベントでストリームを閉じるか。

    候補を後から送る完了（followups_pending）は閉じず、followups で閉じる（specs/028 T24）。
    """
    if typ == "followups":
        return True
    return typ in TERMINAL and not ev.get("followups_pending")
