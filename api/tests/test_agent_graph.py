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
    top = [s for s in steps if s["parent_id"] is None and s["name"] != "system"]
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
    top = next(s for s in done if s["parent_id"] is None and s["name"] != "system")
    assert top["summary"] == "完全一致 0 件 → セマンティック検索で資料 1 件"
    kids = [s for s in done if s["parent_id"] == top["id"]]
    assert [k["label"] for k in kids] == ["検索", "型番のみで再検索", "セマンティック検索で補完"]
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


# ── 調べ残しの見直し（複数の資料を照合する質問で、1 回の検索だけで「資料に無い」と答えない） ──


async def test_gap_answer_after_few_searches_is_sent_back_once() -> None:
    model = FakeToolModel(
        messages=script(
            tool_call("search", query="HP-300 第3版 変更点"),
            AIMessage(content="変更点はトルク値です[1]。在庫数は資料に記載されていません。"),
            tool_call("search", query="SK-300 部品台帳 在庫"),
            AIMessage(content="変更点はトルク値です[1]。在庫は 5 個です[2]。"),
        )
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("HP-300 第3版", "SK-300 在庫 5"))
    state, custom = await run(agent, c, "第3版の変更点と、関連部品の在庫は？")
    assert state["messages"][-1].text == "変更点はトルク値です[1]。在庫は 5 個です[2]。"
    # 差し戻しは記録に残す（下書き・きっかけの語・差し戻した依頼）。技術者があとから追えるように
    review = [e["step"] for e in custom if e["type"] == "step" and e["step"]["name"] == "review"]
    assert [s["status"] for s in review] == ["running", "done"]
    done = review[-1]
    assert done["input"]["draft"] == "変更点はトルク値です[1]。在庫数は資料に記載されていません。"
    assert done["input"]["trigger"] == "記載されていません" and done["input"]["searches"] == 1
    assert "まだ調べていない" in done["output"]["note"]
    # 見直しの依頼は 2 回目の呼び出しの中だけにあり、会話の状態（checkpoint）には残さない
    retry = model.calls[2]
    assert isinstance(retry[-1], HumanMessage) and "まだ調べていない" in retry[-1].text
    assert not any("在庫数は資料に記載されていません" in m.text for m in state["messages"])
    assert sum(isinstance(m, ToolMessage) for m in state["messages"]) == 2


async def test_gap_review_happens_only_once_per_turn() -> None:
    model = FakeToolModel(
        messages=script(
            tool_call("search", query="a"),
            AIMessage(content="資料に記載されていません。"),
            AIMessage(content="やはり資料に記載されていません。"),
        )
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    state, _ = await run(agent, ctx(FakeSearch("本文")), "q")
    assert state["messages"][-1].text == "やはり資料に記載されていません。"
    assert len(model.calls) == 3


async def test_no_gap_review_when_answer_is_complete_or_searched_enough() -> None:
    complete = FakeToolModel(messages=script(tool_call("search", query="a"), AIMessage(content="答え[1]")))
    await run(build_agent(complete, checkpointer=InMemorySaver()), ctx(FakeSearch("本文")), "q")
    assert len(complete.calls) == 2

    searched = FakeToolModel(
        messages=script(
            tool_call("search", query="a"),
            tool_call("search", query="b"),
            tool_call("search", query="c"),
            AIMessage(content="資料に記載されていません。"),
        )
    )
    await run(build_agent(searched, checkpointer=InMemorySaver()), ctx(FakeSearch("本文")), "q")
    assert len(searched.calls) == 4


# ── 後ろで行う処理も記録に残す（「システムの処理」。技術者が追えるように） ──


def system_steps(custom: list[Any]) -> dict[str, dict[str, Any]]:
    return {
        e["step"]["input"]["kind"]: e["step"]
        for e in custom
        if e["type"] == "step" and e["step"]["name"] == "system"
    }


async def test_forced_tool_and_citation_cleanup_are_recorded() -> None:
    model = FakeToolModel(
        messages=script(tool_call("search", query="MX-17"), AIMessage(content="停止する【1】。根拠なし[9]"))
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    _, custom = await run(agent, ctx(FakeSearch("MX-17 は即時停止を推奨する。")), "MX-17 はどうする？")
    sys = system_steps(custom)
    assert sys["force_tool"]["status"] == "done"
    cleanup = sys["citation_cleanup"]
    assert cleanup["input"]["before"] == "停止する【1】。根拠なし[9]"
    assert cleanup["output"]["after"] == "停止する[1]。根拠なし"
    assert cleanup["output"]["removed_numbers"] == [9]
    assert "[9]" in cleanup["summary"]


async def test_step_budget_is_recorded() -> None:
    model = FakeToolModel(
        messages=script(
            tool_call("search", query="a"),
            tool_call("search", query="b"),
            AIMessage(content="まとめ[1]"),
        )
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    _, custom = await run(agent, ctx(FakeSearch("本文"), cfg=AgentCfg(max_steps=3)), "q")
    budget = system_steps(custom)["step_budget"]
    assert budget["input"]["calls"] == 3 and budget["input"]["max_steps"] == 3
    assert "最終回答" in budget["output"]["note"]


async def test_prior_turn_compaction_is_recorded_once() -> None:
    model = FakeToolModel(
        messages=script(
            tool_call("search", query="a"),
            AIMessage(content="一回目[1]"),
            tool_call("search", query="b"),
            AIMessage(content="二回目[1]"),
        )
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    _, first = await run(agent, ctx(FakeSearch("本文")), "一つ目", thread="t3")
    assert "compact_history" not in system_steps(first)
    _, second = await run(agent, ctx(FakeSearch("本文")), "二つ目", thread="t3")
    compact = [
        e for e in second if e["type"] == "step" and e["step"]["input"].get("kind") == "compact_history"
    ]
    assert len(compact) == 1 and compact[0]["step"]["input"]["replaced"] == 1


async def test_summarization_is_recorded() -> None:
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langgraph.runtime import Runtime

    from arag.agent.middleware import RecordedSummarization

    events: list[Any] = []
    mw = RecordedSummarization(
        GenericFakeChatModel(messages=iter([AIMessage(content="これまでの要約")])),
        trigger=("messages", 4),
        keep=("messages", 2),
    )
    msgs = [
        HumanMessage(f"質問{i}", id=f"h{i}") if i % 2 == 0 else AIMessage(f"答え{i}", id=f"a{i}")
        for i in range(6)
    ]
    result = await mw.abefore_model({"messages": msgs}, Runtime(context=None, stream_writer=events.append))
    assert result is not None
    step = events[-1]["step"]
    assert step["name"] == "system" and step["input"]["kind"] == "summarize_history"
    assert step["input"]["messages_before"] == 6 and step["input"]["kept"] == 2
    assert "これまでの要約" in step["output"]["summary"]
