"""会話モデルが失敗したら代替モデルに切り替える（specs/013-llm-keys R6 の見える化）。

LangChain の ModelFallbackMiddleware は最後の例外しか残さず、切り替えたことも画面に出ない。
（例: ローカルの Qwen に繋がらず DeepSeek へ切り替え、DeepSeek が残高不足 → 402 だけが残る）
ここでは
- 主モデルの失敗をログに残し、「モデルを切り替え」のステップで理由を見せる
- 一度切り替えたら、その実行の残りは代替モデルで続ける（毎回タイムアウトを待たない）
- すべて失敗したら、モデルごとの理由をまとめた例外にする
"""

import time
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.language_models import BaseChatModel
from langgraph.errors import GraphBubbleUp

from arag.agent.context import RunContext
from arag.agent.steps import Step, StepClock

log = structlog.get_logger(__name__)


def describe_model_error(e: BaseException) -> str:
    """利用者に見せる短い理由（キーや URL は出さない）。"""
    name = type(e).__name__
    status = getattr(e, "status_code", None)
    if isinstance(status, int):
        if status == 402:
            return "残高が不足しています（402）"
        if status in (401, 403):
            return f"API キーが使えません（{status}）"
        if status == 404:
            return "モデルが見つかりません（404）"
        if status == 429:
            return "利用上限に達しました（429）"
        if status >= 500:
            return f"サーバーでエラーが起きました（{status}）"
        return f"要求が受け付けられませんでした（{status}）"
    if "Timeout" in name:
        return "応答がありません（タイムアウト）"
    if "Connect" in name or isinstance(e, (ConnectionError, OSError)):
        return "接続できません"
    return f"失敗しました（{name}）"


class ModelChainError(RuntimeError):
    """主モデルも代替モデルも失敗した。"""

    def __init__(self, failures: list[tuple[str, BaseException]]) -> None:
        self.failures = failures
        super().__init__(" / ".join(f"{label}: {describe_model_error(e)}" for label, e in failures))

    def user_message(self) -> str:
        lines = "\n".join(f"- {label}: {describe_model_error(e)}" for label, e in self.failures)
        return f"回答の生成に失敗しました。使えるモデルがありませんでした。\n\n{lines}"


class ModelSwitchMiddleware(AgentMiddleware[Any, RunContext]):
    def __init__(self, primary_label: str, fallbacks: list[tuple[str, BaseChatModel]]) -> None:
        super().__init__()
        self.primary_label = primary_label
        self.fallbacks = fallbacks

    async def awrap_model_call(
        self,
        request: ModelRequest[RunContext],
        handler: Callable[[ModelRequest[RunContext]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        ctx = request.runtime.context
        chain: list[tuple[str, BaseChatModel | None]] = [(self.primary_label, None), *self.fallbacks]
        failures: list[tuple[str, BaseException]] = []
        for i in range(ctx.model_index, len(chain)):
            label, model = chain[i]
            started = time.perf_counter()
            ctx.model_label = label
            try:
                resp = await handler(request if model is None else request.override(model=model))
            except GraphBubbleUp:
                raise
            except Exception as e:
                log.warning("model_failed", model=label, error=f"{type(e).__name__}: {str(e)[:300]}")
                failures.append((label, e))
                if i + 1 < len(chain):
                    self._announce(request, label, chain[i + 1][0], e, started)
                continue
            ctx.model_index = i
            return resp
        raise ModelChainError(failures)

    def _announce(
        self, request: ModelRequest[RunContext], frm: str, to: str, e: BaseException, started: float
    ) -> None:
        ctx = request.runtime.context
        ctx.model_switches += 1
        reason = describe_model_error(e)
        clock = StepClock(
            request.runtime.stream_writer,
            Step(
                id=f"switch-model-{ctx.model_switches}",
                name="switch_model",
                label="モデル切り替え",
                status="running",
                input={"from": frm, "to": to},
                summary=f"{frm} が使えないため {to} に切り替えています",
            ),
        )
        clock.t0 = started  # 所要時間は「失敗したモデルを待った時間」
        clock.done(f"{frm}: {reason} → {to} に切り替え", {"from": frm, "to": to, "reason": reason})
