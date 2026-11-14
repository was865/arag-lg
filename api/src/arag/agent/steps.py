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
    # このステップを出した回答の流れの節点（specs/029 R3。古い記録には無い）
    node: str | None = None


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


def elapsed_ms(t0: float) -> int:
    """t0（perf_counter）からの経過ミリ秒。測った処理は最小 1 とする（0 は「測っていない」の意味）。"""
    return max(1, round((time.perf_counter() - t0) * 1000))


def record_system(
    emit: Any, step_id: str, kind: str, label: str, summary: str, *, duration_ms: int = 0, **detail: Any
) -> None:
    """後ろで行った処理を「システムの処理」のステップとして記録に残す（後端の動きは原則すべて記録に出す）。

    detail の input は入力に、output は出力にそのまま入れる。画面では 1 つの畳んだ組にまとめて見せる。
    duration_ms は実際に測った所要時間。測っていない処理は 0 のままで、画面は時間を出さない。
    """
    step = Step(
        id=step_id,
        name="system",
        label=label,
        status="done",
        duration_ms=duration_ms,
        input={"kind": kind, **detail.get("input", {})},
        output=detail.get("output"),
        summary=summary,
    )
    emit({"type": "step", "step": step.model_dump()})


def tag_node(emit: Any, node: str) -> Any:
    """送るステップに節点の名前を付ける（既に付いていれば変えない。specs/029 R3）。"""

    def tagged(ev: dict[str, Any]) -> None:
        step = ev.get("step") if ev.get("type") == "step" else None
        if isinstance(step, dict) and not step.get("node"):
            ev = {**ev, "step": {**step, "node": node}}
        emit(ev)

    return tagged
