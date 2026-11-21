"""検索の計測の口（段の時間と rerank 前の候補）。呼んだタスクの中だけで有効な ContextVar（specs/037 R2）。"""

from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from arag.search.schemas import StageTiming

# 段が終わるたびに呼ばれる（呼び出し側が画面へ逐次送るため。呼んだタスクの中だけで有効）
stage_hook: ContextVar[Callable[[StageTiming], None] | None] = ContextVar("search_stage_hook", default=None)


# rerank の前の候補（融合した順）。画面で「何が候補に上がったか」を見せるために送る
candidates_hook: ContextVar[Callable[[list[dict[str, Any]]], None] | None] = ContextVar(
    "search_candidates_hook", default=None
)
