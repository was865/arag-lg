"""ツール表示のステップ（旧版 UI の ToolCall と同じ形。specs/005-agent R10）。"""

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

StepStatus = Literal["pending", "running", "done", "error"]


class Step(BaseModel):
    id: str
    name: str
    parent_id: str | None = None
    label: str
    status: StepStatus
    duration_ms: int = 0
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] | None = None
    summary: str = ""


class StepClock:
    """子ステップを running → done で送るための小さな道具。"""

    def __init__(self, emit: Any, step: Step) -> None:
        self.emit = emit
        self.step = step
        self.t0 = time.perf_counter()
        emit({"type": "step", "step": step.model_dump()})

    def done(self, summary: str, output: dict[str, Any] | None = None, *, error: bool = False) -> None:
        self.step = self.step.model_copy(
            update={
                "status": "error" if error else "done",
                "duration_ms": round((time.perf_counter() - self.t0) * 1000),
                "summary": summary,
                "output": output,
            }
        )
        self.emit({"type": "step", "step": self.step.model_dump()})
