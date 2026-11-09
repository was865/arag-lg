"""エージェントの流れ（偽モデル。specs/005-agent B4・B5、R18・R20）。"""

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from arag.agent.config import AgentCfg
from arag.agent.context import RunContext
from arag.agent.graph import build_agent
from arag.agent.middleware import PRIOR_TOOL_PLACEHOLDER
from arag.auth.principal import Principal

from .agent_fakes import FakeSearch, FakeToolModel, null_sessionmaker, script, tool_call


def ctx(search: FakeSearch, **kw: Any) -> RunContext:
    return RunContext(
        principal=Principal(user_id="u"), sessionmaker=null_sessionmaker, search=search, question="q", **kw
    )


async def run(agent: Any, c: RunContext, q: str, thread: str = "t") -> tuple[dict[str, Any], list[Any]]:
    custom: list[Any] = []
    cfg = {"configurable": {"thread_id": thread}}
    async for mode, chunk in agent.astream(
        {"messages": [HumanMessage(q)]}, cfg, context=c, stream_mode=["messages", "custom"]
    ):
        if mode == "custom":
            custom.append(chunk)
    return (await agent.aget_state(cfg)).values, custom


async def test_search_then_answer_with_citation_cleanup() -> None:
    model = FakeToolModel(
        messages=script(tool_call("search", query="MX-17"), AIMessage(content="停止する【1】。根拠なし[9]"))
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("MX-17 は即時停止を推奨する。"))
    state, custom = await run(agent, c, "MX-17 はどうする？")
    assert state["messages"][-1].text == "停止する[1]。根拠なし"
    tool_msg = next(m for m in state["messages"] if isinstance(m, ToolMessage))
    assert '<資料 n="1"' in tool_msg.text
    steps = [e["step"] for e in custom if e["type"] == "step"]
    top = [s for s in steps if s["parent_id"] is None]
    assert [s["status"] for s in top] == ["running", "done"] and top[0]["name"] == "search"
    assert top[1]["summary"] == "資料 1 件"
    assert any(s["parent_id"] == top[0]["id"] for s in steps)  # 検索の子ステップ
    sys = model.calls[0][0]
    assert isinstance(sys, SystemMessage) and "<資料" in sys.text and "必ず付ける" in sys.text
    assert c.stats.tool_calls == 1 and c.stats.model_calls == 2
    # ターンの最初の呼び出しはツールを必ず使わせる（前のターンの記憶だけで引用なしに答えない）
    assert model.tool_choices == ["any", None]


class KeywordMissSearch(FakeSearch):
    """語の完全一致（must_contain）では何も返さない検索。"""

    async def __call__(self, _s: Any, _p: Any, req: Any) -> Any:
        res = await super().__call__(_s, _p, req)
        return res.model_copy(update={"hits": []}) if req.must_contain else res


async def test_keyword_fallback_is_explained_in_steps() -> None:
    model = FakeToolModel(
        messages=script(
            tool_call("keyword_search", terms=["MX-17", "異常時の対応"]), AIMessage(content="停止する[1]")
        )
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    _, custom = await run(agent, ctx(KeywordMissSearch("MX-17 は即時停止を推奨する。")), "MX-17 の異常時は？")
    done = [e["step"] for e in custom if e["type"] == "step" and e["step"]["status"] == "done"]
    top = next(s for s in done if s["parent_id"] is None)
    assert top["summary"] == "完全一致 0 件 → 意味検索で資料 1 件"
    kids = [s for s in done if s["parent_id"] == top["id"]]
    assert [k["label"] for k in kids] == ["検索", "意味検索で補う"]
    assert kids[0]["summary"].startswith("0 件（「MX-17」「異常時の対応」をすべて含む箇所なし")


async def test_step_budget_forces_final_answer_without_tools() -> None:
    model = FakeToolModel(
        messages=script(
            tool_call("search", query="a"),
            tool_call("search", query="b"),
            AIMessage(content="まとめ[1]"),
        )
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("本文"), cfg=AgentCfg(max_steps=3))
    state, _ = await run(agent, c, "q")
    assert state["messages"][-1].text == "まとめ[1]"
    assert model.tool_counts == [6, 6, 0]  # 3 回目はツールなし
    assert "最終回答" in model.calls[2][0].text


async def test_prior_turn_tool_results_are_compacted() -> None:
    model = FakeToolModel(
        messages=script(
            tool_call("search", query="a"),
            AIMessage(content="一回目[1]"),
            AIMessage(content="二回目"),
        )
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    await run(agent, ctx(FakeSearch("本文")), "一つ目", thread="t2")
    await run(agent, ctx(FakeSearch("本文")), "二つ目", thread="t2")
    second = model.calls[-1]
    tools = [m for m in second if isinstance(m, ToolMessage)]
    assert tools and all(m.text == PRIOR_TOOL_PLACEHOLDER for m in tools)


async def test_tool_failure_becomes_error_step_and_message() -> None:
    class Boom(FakeSearch):
        async def __call__(self, *_a: Any) -> Any:
            raise RuntimeError("qdrant down")

    model = FakeToolModel(messages=script(tool_call("search", query="a"), AIMessage(content="失敗しました")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(Boom())
    state, custom = await run(agent, c, "q")
    tm = next(m for m in state["messages"] if isinstance(m, ToolMessage))
    assert tm.status == "error" and "失敗" in tm.text
    errs = [e["step"] for e in custom if e["type"] == "step" and e["step"]["status"] == "error"]
    assert errs and c.stats.tool_errors == 1


async def test_tool_choice_not_forced_without_citations() -> None:
    model = FakeToolModel(messages=script(AIMessage(content="こんにちは")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    await run(agent, ctx(FakeSearch(), cfg=AgentCfg(require_citations=False)), "こんにちは")
    assert model.tool_choices == [None]
