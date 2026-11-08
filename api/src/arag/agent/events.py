"""run のイベント（SSE の契約。specs/005-agent R10）。OpenAPI に出して TS 型を生成する。"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from arag.agent.steps import Step

NoAnswerReason = Literal["no_sources", "step_budget_exhausted", "tool_failed", "generation_failed"]


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
    | RunFailed
    | RunCancelled,
    Field(discriminator="type"),
]
RUN_EVENT = TypeAdapter(RunEvent)
TERMINAL = frozenset({"run.completed", "run.failed", "run.cancelled"})
