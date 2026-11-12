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


def top_steps(custom: list[Any]) -> list[dict[str, Any]]:
    """モデルのツールと、システムが行った検索の親ステップ（システムの処理・質問の理解は除く）。"""
    steps = [e["step"] for e in custom if e["type"] == "step"]
    return [s for s in steps if s["parent_id"] is None and s["name"] not in {"system", "understand"}]


def own_steps(custom: list[Any]) -> list[dict[str, Any]]:
    """モデルが呼んだツールのステップ（システムの最初の検索は除く）。"""
    return [s for s in top_steps(custom) if not s["id"].startswith("primer-")]


# ── 最初の検索はシステムが行う（specs/026。モデルが検索するかどうかに任せない） ──


async def test_system_searches_first_and_model_can_answer_directly() -> None:
    model = FakeToolModel(messages=script(AIMessage(content="停止する【1】。根拠なし[9]")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("MX-17 は即時停止を推奨する。"))
    state, custom = await run(agent, c, "MX-17 はどうする？")
    assert state["messages"][-1].text == "停止する[1]。根拠なし"
    # システムの検索は「検索」のステップとして記録に出る（by=system で見分ける）
    primer = [s for s in top_steps(custom) if s["id"] == "primer-1"]
    assert [s["status"] for s in primer] == ["running", "done"]
    assert primer[1]["input"] == {"query": "MX-17 はどうする？", "by": "system"}
    assert primer[1]["summary"] == "資料 1 件"
    assert any(e["step"]["parent_id"] == "primer-1" for e in custom if e["type"] == "step")
    # 検索結果は質問に添えてモデルに渡すが、会話の状態には保存しない
    human = next(m for m in model.calls[0] if isinstance(m, HumanMessage))
    assert human.text.startswith("MX-17 はどうする？") and '<資料 n="1"' in human.text
    assert "<検索結果>" in human.text
    saved = next(m for m in state["messages"] if isinstance(m, HumanMessage))
    assert saved.text == "MX-17 はどうする？"
    assert not any(isinstance(m, ToolMessage) for m in state["messages"])
    # ツールは強制しない（どのモデルでも同じ流れで動く）。7 つとも渡す
    assert model.tool_choices == [None] and model.tool_counts == [7]
    assert c.stats.primer_searches == 1 and c.stats.tool_calls == 0 and c.stats.model_calls == 1
    sys = model.calls[0][0]
    assert isinstance(sys, SystemMessage) and "<検索結果>" in sys.text and "必ず付ける" in sys.text


async def test_model_can_still_search_after_primer() -> None:
    model = FakeToolModel(
        messages=script(tool_call("search", query="MX-17 手順"), AIMessage(content="停止する[1]"))
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("MX-17 は即時停止を推奨する。"))
    _, custom = await run(agent, c, "MX-17 はどうする？")
    own = own_steps(custom)
    assert [s["status"] for s in own] == ["running", "done"] and own[0]["name"] == "search"
    assert "by" not in own[1]["input"]
    assert c.stats.tool_calls == 1 and c.stats.model_calls == 2
    # 2 回目の呼び出しでも、最初の検索結果は質問に添えたまま
    human = next(m for m in model.calls[1] if isinstance(m, HumanMessage))
    assert "<検索結果>" in human.text


def utility(*outputs: str) -> FakeToolModel:
    return FakeToolModel(messages=script(*(AIMessage(content=o) for o in outputs)))


async def test_followup_is_searched_with_rewritten_query() -> None:
    model = FakeToolModel(messages=script(AIMessage(content="一回目[1]"), AIMessage(content="二回目[1]")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    search = FakeSearch("SK-300 の仕入先は Aster Seals。")
    u = utility(
        '{"kind": "docs", "queries": ["SK-300 の単価"], "table": false}',
        '{"kind": "docs", "queries": ["SK-300 の仕入先"], "table": false}',
    )
    await run(agent, ctx(search, utility_model=u), "SK-300 の単価は？", thread="f1")
    _, custom = await run(agent, ctx(search, utility_model=u), "それの仕入先は？", thread="f1")
    # 追質問は指示語を含むので、整理したクエリだけで検索する（質問文では検索しない）
    assert [r.query for r in search.requests] == ["SK-300 の単価は？", "SK-300 の単価", "SK-300 の仕入先"]
    understood = [e["step"] for e in custom if e["type"] == "step" and e["step"]["name"] == "understand"]
    assert understood[-1]["output"]["queries"] == ["SK-300 の仕入先"]
    assert understood[-1]["input"]["history"] is True
    # 整理には直近の会話を渡す
    asked = u.calls[1][-1].text
    assert "SK-300 の単価は？" in asked and "それの仕入先は？" in asked


async def test_chat_gets_no_search_results() -> None:
    model = FakeToolModel(
        messages=script(AIMessage(content="一回目[1]"), AIMessage(content="どういたしまして"))
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    search = FakeSearch("本文")
    u = utility('{"kind": "docs", "queries": ["q"]}', '{"kind": "chat", "queries": [], "table": false}')
    await run(agent, ctx(search, utility_model=u), "質問", thread="c1")
    n = len(search.requests)
    c = ctx(search, utility_model=u)
    await run(agent, c, "ありがとう", thread="c1")
    assert len(search.requests) == n  # 雑談では検索しない
    human = [m for m in model.calls[-1] if isinstance(m, HumanMessage)][-1]
    assert human.text == "ありがとう"
    assert c.primer is not None and c.primer.kind == "chat"


async def test_unreadable_understanding_falls_back_to_the_question() -> None:
    model = FakeToolModel(messages=script(AIMessage(content="答え[1]")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    search = FakeSearch("本文")
    _, custom = await run(agent, ctx(search, utility_model=utility("わかりません")), "保存期間は？")
    assert [r.query for r in search.requests] == ["保存期間は？"]
    understood = [e["step"] for e in custom if e["type"] == "step" and e["step"]["name"] == "understand"]
    assert understood[-1]["status"] == "done" and "JSON" in understood[-1]["output"]["error"]


async def test_extra_queries_are_searched_and_duplicates_dropped() -> None:
    model = FakeToolModel(messages=script(AIMessage(content="答え[1]")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    search = FakeSearch("第2版は 45 N·m。")
    u = utility('{"kind": "docs", "queries": ["第2版 締付トルク", "第3版 締付トルク"], "table": false}')
    c = ctx(search, utility_model=u)
    await run(agent, c, "第2版と第3版のトルクの違いは？")
    assert [r.query for r in search.requests] == [
        "第2版と第3版のトルクの違いは？",
        "第2版 締付トルク",
        "第3版 締付トルク",
    ]
    assert c.primer is not None
    # 同じ資料は 1 度だけ渡す
    assert c.primer.text.count('<資料 n="1"') == 1 and "（資料 [1] は上と同じ）" in c.primer.text


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
    top = next(s for s in done if s["name"] == "keyword_search")
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
    assert model.tool_counts == [7, 7, 0]  # 3 回目はツールなし
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
    # システムの最初の検索と、モデルの検索の両方が失敗として残る
    assert [e["id"].startswith("primer-") for e in errs] == [True, False] and c.stats.tool_errors == 2


# ── 調べ残しの見直し（複数の資料を照合する質問で、1 回の検索だけで「資料に無い」と答えない） ──


async def test_gap_answer_is_sent_back_once() -> None:
    model = FakeToolModel(
        messages=script(
            AIMessage(content="変更点はトルク値です[1]。在庫数は資料に記載されていません。"),
            tool_call("search", query="SK-300 部品台帳 在庫"),
            AIMessage(content="変更点はトルク値です[1]。在庫は SK-300 のとおりです[2]。"),
        )
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("HP-300 第3版", "SK-300 在庫"))
    state, custom = await run(agent, c, "第3版の変更点と、関連部品の在庫は？")
    assert state["messages"][-1].text == "変更点はトルク値です[1]。在庫は SK-300 のとおりです[2]。"
    # 差し戻しは記録に残す（下書き・きっかけの語・差し戻した依頼）。技術者があとから追えるように
    review = [e["step"] for e in custom if e["type"] == "step" and e["step"]["name"] == "review"]
    assert [s["status"] for s in review] == ["running", "done"]
    done = review[-1]
    assert done["input"]["kind"] == "gap" and done["label"] == "調べ残しの見直し"
    assert done["input"]["draft"] == "変更点はトルク値です[1]。在庫数は資料に記載されていません。"
    assert done["input"]["trigger"] == "記載されていません" and done["input"]["searches"] == 1
    assert "まだ調べていない" in done["output"]["note"] and done["output"]["next_tools"] == ["search"]
    # 見直しの依頼はその呼び出しの中だけにあり、会話の状態（checkpoint）には残さない
    retry = model.calls[1]
    assert isinstance(retry[-1], HumanMessage) and "まだ調べていない" in retry[-1].text
    assert not any("在庫数は資料に記載されていません" in m.text for m in state["messages"])
    assert sum(isinstance(m, ToolMessage) for m in state["messages"]) == 1


async def test_gap_review_happens_only_once_per_turn() -> None:
    model = FakeToolModel(
        messages=script(
            AIMessage(content="資料に記載されていません。"),
            AIMessage(content="やはり資料に記載されていません。"),
        )
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    state, _ = await run(agent, ctx(FakeSearch("本文")), "q")
    assert state["messages"][-1].text == "やはり資料に記載されていません。"
    assert len(model.calls) == 2


async def test_no_gap_review_when_answer_is_complete_or_searched_enough() -> None:
    complete = FakeToolModel(messages=script(AIMessage(content="答え[1]")))
    await run(build_agent(complete, checkpointer=InMemorySaver()), ctx(FakeSearch("本文")), "q")
    assert len(complete.calls) == 1

    searched = FakeToolModel(
        messages=script(
            tool_call("search", query="a"),
            tool_call("search", query="b"),
            AIMessage(content="資料に記載されていません。"),
        )
    )
    await run(build_agent(searched, checkpointer=InMemorySaver()), ctx(FakeSearch("本文")), "q")
    assert len(searched.calls) == 3


# ── 表の集計と数字の確認（specs/026 ④） ──

TABLE = "| 部品 | 在庫 | 発注点 |\n|---|---|---|\n| P-1042 | 6 | 10 |\n| P-1043 | 4 | 4 |"


async def test_table_question_answered_by_eye_is_sent_back() -> None:
    model = FakeToolModel(
        messages=script(
            AIMessage(content="P-1042 と P-1043 です[1]"),
            AIMessage(content="P-1042 です[1]"),
        )
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    u = utility('{"kind": "docs", "queries": ["在庫が発注点を下回る部品"], "table": true}')
    c = ctx(FakeSearch(TABLE), utility_model=u)
    state, custom = await run(agent, c, "在庫が発注点を下回る部品は？")
    assert state["messages"][-1].text == "P-1042 です[1]"
    review = [e["step"] for e in custom if e["type"] == "step" and e["step"]["name"] == "review"][-1]
    assert review["input"]["kind"] == "table" and review["label"] == "表の集計の確認"
    assert "table_query" in review["output"]["note"]
    assert c.stats.table_reviews == 1 and len(model.calls) == 2


async def test_numbers_missing_from_sources_are_sent_back_and_recorded() -> None:
    model = FakeToolModel(
        messages=script(
            AIMessage(content="単価は 17,800 円です[1]"),
            AIMessage(content="単価は 17,800 円です[1]"),
        )
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("シールキット SK-300 の単価は 18,400 円。"))
    _, custom = await run(agent, c, "SK-300 の単価は？")
    review = [e["step"] for e in custom if e["type"] == "step" and e["step"]["name"] == "review"][-1]
    assert review["input"]["kind"] == "numbers" and "17,800" in review["input"]["trigger"]
    assert "17,800" in review["output"]["note"]
    # 差し戻しても残った数字は、照合の結果として記録に残す（画面で注意として示す）
    check = system_steps(custom)["number_check"]
    assert check["output"]["unverified"] == ["17,800"] and "17,800" in check["summary"]
    assert c.stats.number_reviews == 1 and len(model.calls) == 2


async def test_numbers_found_in_sources_pass_the_check() -> None:
    model = FakeToolModel(messages=script(AIMessage(content="単価は 18,400 円、保存は 14 日です[1]")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    _, custom = await run(agent, ctx(FakeSearch("SK-300 の単価は 18400 円。保存は十四日。")), "SK-300 は？")
    check = system_steps(custom)["number_check"]
    assert check["output"]["unverified"] == [] and "すべて確認" in check["summary"]
    assert len(model.calls) == 1


# ── 後ろで行う処理も記録に残す（「システムの処理」。技術者が追えるように） ──


def system_steps(custom: list[Any]) -> dict[str, dict[str, Any]]:
    return {
        e["step"]["input"]["kind"]: e["step"]
        for e in custom
        if e["type"] == "step" and e["step"]["name"] == "system"
    }


async def test_citation_cleanup_is_recorded() -> None:
    model = FakeToolModel(messages=script(AIMessage(content="停止する【1】。根拠なし[9]")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    _, custom = await run(agent, ctx(FakeSearch("MX-17 は即時停止を推奨する。")), "MX-17 はどうする？")
    sys = system_steps(custom)
    assert "force_tool" not in sys  # ツールは強制しない
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


def test_send_back_notes_ask_to_keep_citation_numbers() -> None:
    from arag.agent.middleware import GAP_NOTE, NUMBER_NOTE, TABLE_NOTE

    for note in (GAP_NOTE, TABLE_NOTE, NUMBER_NOTE):
        assert "書き直すときも" in note and "出典番号" in note
