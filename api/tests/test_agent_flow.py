"""回答の流れの節点と辺（specs/029 T4〜T10）。"""

from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from arag.agent.context import Completion, RunContext, RunHooks
from arag.agent.flow import (
    FRESH,
    NODES,
    route_after_finalize,
    route_after_guard,
    route_after_review,
    route_after_understand,
)
from arag.agent.graph import build_agent
from arag.agent.runner import _repair_dangling_tool_calls, _stream, _Turn
from arag.auth.principal import Principal

from .agent_fakes import FakeSearch, FakeToolModel, null_sessionmaker, script, tool_call
from .test_agent_flow_snapshots import ListSink


def ctx(search: FakeSearch, **kw: Any) -> RunContext:
    return RunContext(
        principal=Principal(user_id="u"), sessionmaker=null_sessionmaker, search=search, question="q", **kw
    )


# ── 辺は状態だけを見る純関数 ──


def test_routes_read_only_the_state() -> None:
    assert route_after_understand({"messages": [], "understanding": {"kind": "chat"}}) == "chat"
    assert route_after_understand({"messages": [], "understanding": {"kind": "docs"}}) == "docs"
    assert route_after_understand({"messages": [], "understanding": None}) == "docs"
    assert route_after_guard({"messages": [], "guard": "retry"}) == "retry"
    assert route_after_guard({"messages": [], "guard": "use_draft"}) == "use_draft"
    assert route_after_guard({"messages": [], "guard": "ok"}) == "ok"
    assert route_after_review({"messages": [], "send_back": {"id": "review-1"}}) == "send_back"
    assert route_after_review({"messages": [], "send_back": None}) == "pass"
    assert route_after_finalize({"messages": [], "followups": True}) == "followups"
    assert route_after_finalize({"messages": []}) == "end"


def test_graph_has_the_declared_nodes_and_edges() -> None:
    agent = build_agent(FakeToolModel(messages=script()))
    g = agent.get_graph()
    assert [n for n in g.nodes if not n.startswith("__")] == [n.id for n in NODES]
    edges = {(e.source, e.target, e.data) for e in g.edges}
    assert ("understand", "investigate", "chat") in edges
    assert ("understand", "primer_search", "docs") in edges
    assert ("guard", "investigate", "retry") in edges
    assert ("guard", "finalize", "use_draft") in edges
    assert ("review", "investigate", "send_back") in edges
    assert ("review", "finalize", "pass") in edges


# ── ステップに節点の名前（R3） ──


async def stream(agent: Any, c: RunContext, q: str, thread: str = "t") -> list[dict[str, Any]]:
    sink = ListSink()
    await _stream(agent, {"configurable": {"thread_id": thread}}, c, sink, _Turn(), q)  # type: ignore[arg-type]
    return sink.events


def nodes_of(events: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    return [
        (e["step"]["id"], e["step"]["status"], e["step"].get("node", ""))
        for e in events
        if e["type"] == "step" and e["step"].get("parent_id") is None
    ]


async def test_every_step_names_its_node() -> None:
    model = FakeToolModel(
        messages=script(
            AIMessage(content="変更点はトルク値です[1]。在庫数は資料に記載されていません。"),
            tool_call("search", query="SK-300 在庫"),
            AIMessage(content="<think>考え</think>在庫は 6 個です[2]。"),
        )
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    events = await stream(agent, ctx(FakeSearch("HP-300 第3版", "SK-300 在庫 6")), "在庫は？")
    steps = [e["step"] for e in events if e["type"] == "step"]
    assert all(s.get("node") for s in steps), [s["id"] for s in steps if not s.get("node")]
    got = {(sid, node) for sid, _, node in nodes_of(events)}
    assert ("understand", "understand") in got
    assert ("primer-1", "understand") in got  # 初回は質問文での検索を理解と並行に行う
    assert ("review-1", "review") in got  # 差し戻しの始まりと終わりは確認の節点のもの
    assert ("system-number-check", "finalize") in got and ("system-citation-cleanup", "finalize") in got
    assert any(sid.startswith("call_") and node == "investigate" for sid, node in got)
    assert any(sid.startswith("reasoning-") and node == "investigate" for sid, node in got)
    # 子のステップ（検索の中の段）にも節点が付く
    assert all(s["node"] for s in steps if s.get("parent_id"))


async def test_extra_queries_are_searched_in_primer_search() -> None:
    u = FakeToolModel(
        messages=script(AIMessage(content='{"kind": "docs", "queries": ["a", "b"], "table": false}'))
    )
    model = FakeToolModel(messages=script(AIMessage(content="答え[1]")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    events = await stream(agent, ctx(FakeSearch("本文"), utility_model=u), "質問")
    got = {(sid, node) for sid, _, node in nodes_of(events)}
    assert {("primer-1", "understand"), ("primer-2", "primer_search"), ("primer-3", "primer_search")} <= got


# ── 状態はターンごとに戻す・古い checkpoint を読める ──


async def test_flow_state_is_reset_each_turn() -> None:
    model = FakeToolModel(
        messages=script(
            AIMessage(content="資料に記載されていません。"),
            AIMessage(content="一回目[1]"),
            AIMessage(content="二回目[1]"),
        )
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "r"}}
    await stream(agent, ctx(FakeSearch("本文")), "一つ目", thread="r")
    first = (await agent.aget_state(cfg)).values
    assert first["reviews_done"] == ["gap"] and first["draft"] is not None and first["outcome"] == "answered"
    await stream(agent, ctx(FakeSearch("本文")), "二つ目", thread="r")
    second = (await agent.aget_state(cfg)).values
    assert second["reviews_done"] == [] and second["draft"] is None and second["chain"] == 0
    assert [m.text for m in second["messages"] if isinstance(m, AIMessage)] == ["一回目[1]", "二回目[1]"]
    assert set(FRESH) <= set(second)


async def test_reads_a_thread_saved_by_the_previous_agent() -> None:
    """作り直しの前（create_agent だけのグラフ）が保存したスレッドの続きを、新しいグラフで答えられる。"""
    saver = InMemorySaver()
    old = create_agent(
        FakeToolModel(messages=script()),
        tools=[],
        checkpointer=saver,
    )
    cfg = {"configurable": {"thread_id": "old"}}
    await old.aupdate_state(
        cfg,
        {
            "messages": [
                HumanMessage("一つ目"),
                AIMessage(content="", tool_calls=[{"name": "search", "args": {}, "id": "c1"}]),
                ToolMessage(content="結果", tool_call_id="c1", name="search"),
                AIMessage(content="一回目[1]"),
            ]
        },
        as_node="model",
    )
    model = FakeToolModel(messages=script(AIMessage(content="二回目[1]")))
    agent = build_agent(model, checkpointer=saver)
    events = await stream(agent, ctx(FakeSearch("本文")), "二つ目", thread="old")
    assert model.calls[0][1].text == "一つ目"  # 前のターンが見えている
    compact = [
        e for e in events if e["type"] == "step" and e["step"]["input"].get("kind") == "compact_history"
    ]
    assert len(compact) == 1
    texts = [m.text for m in (await agent.aget_state(cfg)).values["messages"]]
    assert texts[0] == "一つ目" and texts[-1] == "二回目[1]"


async def test_dangling_tool_calls_are_closed_on_the_outer_graph() -> None:
    agent = build_agent(FakeToolModel(messages=script()), checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "d"}}
    await agent.aupdate_state(
        cfg,
        {
            "messages": [
                HumanMessage("q"),
                AIMessage(content="", tool_calls=[{"name": "search", "args": {}, "id": "x"}]),
            ]
        },
        as_node="investigate",
    )
    await _repair_dangling_tool_calls(agent, cfg)
    msgs = (await agent.aget_state(cfg)).values["messages"]
    assert isinstance(msgs[-1], ToolMessage) and msgs[-1].tool_call_id == "x" and msgs[-1].status == "error"


# ── runner への出入り（確定・続けて聞く・画像） ──


async def test_finalize_hands_the_answer_to_the_runner_before_followups() -> None:
    order: list[str] = []
    got: list[Completion] = []

    async def completed(c: Completion) -> None:
        order.append("completed")
        got.append(c)

    async def followups() -> list[str]:
        order.append("followups")
        return ["次の質問は？"]

    model = FakeToolModel(messages=script(AIMessage(content="停止する【1】。")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("MX-17 は即時停止を推奨する。"))
    c.hooks = RunHooks(completed=completed, followups=followups)
    await stream(agent, c, "MX-17 は？", thread="h")
    assert order == ["completed", "followups"]
    [done] = got
    assert done.answer == "停止する[1]。" and done.reason is None and done.followups
    assert list(done.citations.cmap) == [1]
    state = (await agent.aget_state({"configurable": {"thread_id": "h"}})).values
    assert state["suggestions"] == ["次の質問は？"] and state["outcome"] == "answered"


async def test_no_followups_for_chat_or_no_answer() -> None:
    calls: list[Completion] = []

    async def completed(c: Completion) -> None:
        calls.append(c)

    async def followups() -> list[str]:
        raise AssertionError("呼ばれないはず")

    u = FakeToolModel(messages=script(AIMessage(content='{"kind": "chat", "queries": []}')))
    agent = build_agent(FakeToolModel(messages=script(AIMessage(content="どういたしまして"))))
    c = ctx(FakeSearch("本文"), utility_model=u)
    c.hooks = RunHooks(completed=completed, followups=followups)
    await stream(agent, c, "ありがとう")
    agent = build_agent(FakeToolModel(messages=script(AIMessage(content=""), AIMessage(content=""))))
    c = ctx(FakeSearch("本文"))
    c.hooks = RunHooks(completed=completed, followups=followups)
    await stream(agent, c, "q")
    assert [(x.followups, x.reason) for x in calls] == [(False, None), (False, "empty_generation")]
    assert calls[1].answer.startswith("回答を生成できませんでした")


async def test_read_image_adds_the_description_to_the_question() -> None:
    async def read(question: str) -> str:
        assert question == "この部品は？"
        return "銘板に SK-300 とある"

    model = FakeToolModel(messages=script(AIMessage(content="SK-300 です[1]")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("SK-300"))
    c.hooks = RunHooks(read_image=read, image_id="i1")
    events = await stream(agent, c, "この部品は？", thread="img")
    img = [e["step"] for e in events if e["type"] == "step" and e["step"]["id"] == "img-i1"]
    assert [(s["status"], s["node"]) for s in img] == [("running", "read_image"), ("done", "read_image")]
    assert img[-1]["output"] == {"description": "銘板に SK-300 とある"}
    saved = (await agent.aget_state({"configurable": {"thread_id": "img"}})).values["messages"][0]
    assert "<image_description>\n銘板に SK-300 とある" in saved.text and c.question == saved.text


async def test_unreadable_image_does_not_stop_the_answer() -> None:
    async def read(_q: str) -> str:
        raise RuntimeError("読めない")

    model = FakeToolModel(messages=script(AIMessage(content="答え[1]")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("本文"))
    c.hooks = RunHooks(read_image=read, image_id="i2")
    events = await stream(agent, c, "これは？")
    img = [e["step"] for e in events if e["type"] == "step" and e["step"]["id"] == "img-i2"][-1]
    assert img["status"] == "error" and img["output"] == {"error": "読めない"}
    assert "（添付画像は読み取れませんでした）" in model.calls[0][1].text
