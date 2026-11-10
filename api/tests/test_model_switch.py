"""会話モデルの切り替えを見せる（主モデル → 代替モデル）。"""

from typing import Any

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from arag.agent.graph import build_agent
from arag.agent.model_switch import ModelChainError, describe_model_error

from .agent_fakes import FailingModel, FakeSearch, FakeToolModel, StatusError, script, tool_call
from .test_agent_graph import ctx, run


def test_describe_model_error() -> None:
    assert describe_model_error(StatusError(402)) == "残高が不足しています（402）"
    assert describe_model_error(StatusError(401)) == "API キーが使えません（401）"
    assert describe_model_error(ConnectionError("refused")) == "接続できません"

    class APITimeoutError(Exception):
        pass

    assert describe_model_error(APITimeoutError()) == "応答がありません（タイムアウト）"


def _steps(custom: list[Any]) -> list[dict[str, Any]]:
    return [e["step"] for e in custom if e["type"] == "step" and e["step"]["status"] == "done"]


async def test_switches_once_and_shows_why() -> None:
    primary = FailingModel(messages=script(), error=ConnectionError("down"))
    backup = FakeToolModel(
        messages=script(tool_call("search", query="MX-17"), AIMessage(content="停止する[1]"))
    )
    agent = build_agent(
        primary,
        fallback=backup,
        model_label="Qwen3 8B",
        fallback_label="DeepSeek",
        checkpointer=InMemorySaver(),
    )
    state, custom = await run(agent, ctx(FakeSearch("MX-17 は即時停止を推奨する。")), "MX-17 は？")
    assert state["messages"][-1].text == "停止する[1]"
    switches = [s for s in _steps(custom) if s["name"] == "switch_model"]
    assert len(switches) == 1
    assert switches[0]["summary"] == "Qwen3 8B: 接続できません → DeepSeek で続けます"
    assert switches[0]["output"]["reason"] == "接続できません" and switches[0]["duration_ms"] >= 0
    # 切り替えたあとは主モデルを試し直さない（毎回タイムアウトを待たない）
    assert primary.failures == 1 and len(backup.calls) == 2


async def test_all_models_fail_with_each_reason() -> None:
    primary = FailingModel(messages=script(), error=ConnectionError("down"))
    backup = FailingModel(messages=script(), error=StatusError(402))
    agent = build_agent(
        primary,
        fallback=backup,
        model_label="Qwen3 8B",
        fallback_label="DeepSeek",
        checkpointer=InMemorySaver(),
    )
    try:
        await run(agent, ctx(FakeSearch("x")), "MX-17 は？")
    except ModelChainError as e:
        msg = e.user_message()
    else:
        raise AssertionError("ModelChainError が出るはず")
    assert "- Qwen3 8B: 接続できません" in msg and "- DeepSeek: 残高が不足しています（402）" in msg
