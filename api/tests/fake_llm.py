"""テスト用の偽チャットモデル。"""

from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class ScriptedChatModel(BaseChatModel):
    """最後のメッセージの本文を見て応答を決める。fail_when を含めば例外。"""

    reply_prefix: str = "この塊は"
    fail_when: str | None = None
    calls: list[list[BaseMessage]] = Field(default_factory=list)
    usage: dict[str, Any] = Field(
        default_factory=lambda: {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
            "input_token_details": {"cache_read": 80},
        }
    )

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _reply(self, messages: list[BaseMessage]) -> ChatResult:
        self.calls.append(messages)
        last = messages[-1].content
        text = (
            last
            if isinstance(last, str)
            else " ".join(str(b.get("text", "")) for b in last if isinstance(b, dict))
        )
        if self.fail_when and self.fail_when in text:
            raise RuntimeError("偽の失敗")
        chunk = text.split("<chunk>")[-1].split("</chunk>")[0].strip()[:10]
        msg = AIMessage(
            content=f"{self.reply_prefix}「{chunk}」について述べている。", usage_metadata=self.usage
        )  # type: ignore[arg-type]
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._reply(messages)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._reply(messages)
