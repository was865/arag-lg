"""エージェントの流れ（偽モデル。specs/005-agent B4・B5、R18・R20）。"""

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from arag.agent.config import AgentCfg
from arag.agent.context import RunContext
from arag.agent.graph import build_agent
from arag.agent.middleware import (
    ANNOUNCE_NOTE,
    PRIOR_NOTE,
    PRIOR_TOOL_PLACEHOLDER,
    is_announce_only,
    prior_placeholder,
)
from arag.agent.prior import cited_documents, turns
from arag.agent.understand import history_text
from arag.auth.principal import Principal

from .agent_fakes import FakeSearch, FakeToolModel, null_sessionmaker, script, tool_call


def ctx(search: FakeSearch, **kw: Any) -> RunContext:
    return RunContext(
        principal=Principal(user_id="u"), sessionmaker=null_sessionmaker, search=search, question="q", **kw
    )


async def run(agent: Any, c: RunContext, q: str, thread: str = "t") -> tuple[dict[str, Any], list[Any]]:
    custom: list[Any] = []
    cfg = {"configurable": {"thread_id": thread}}
    # 調査は部分グラフなので、その中のステップも受けるよう subgraphs=True で流す（specs/029）
    async for _ns, mode, chunk in agent.astream(
        {"messages": [HumanMessage(q)]}, cfg, context=c, stream_mode=["messages", "custom"], subgraphs=True
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
    assert primer[1]["input"]["by"] == "system" and primer[1]["input"]["role"] == "question"
    assert primer[1]["label"] == "質問文で検索"
    assert primer[1]["summary"] == "「MX-17 はどうする？」・資料 1 件"
    assert any(e["step"]["parent_id"] == "primer-1" for e in custom if e["type"] == "step")
    # 検索結果は質問に添えてモデルに渡すが、会話の状態には保存しない
    human = next(m for m in model.calls[0] if isinstance(m, HumanMessage))
    assert human.text.startswith("MX-17 はどうする？") and '<資料 n="1"' in human.text
    assert "<検索結果>" in human.text
    saved = next(m for m in state["messages"] if isinstance(m, HumanMessage))
    assert saved.text == "MX-17 はどうする？"
    assert not any(isinstance(m, ToolMessage) for m in state["messages"])
    # ツールは強制しない（どのモデルでも同じ流れで動く）。9 つとも渡す
    assert model.tool_choices == [None] and model.tool_counts == [9]
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
    assert [r.query for r in search.requests] == [
        "SK-300 の単価は？",
        "SK-300 の仕入先",
    ]  # 1 回目の「SK-300 の単価」は質問文とほぼ同じなので省かれる
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
    assert model.tool_counts == [9, 9, 0]  # 3 回目はツールなし
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
    # 本文は省くが、どの文書を調べたかは残す
    assert tools and all(
        m.text.startswith("（前のターンの資料: 「") and "本文は省略" in m.text for m in tools
    )


def test_prior_placeholder_lists_documents_once() -> None:
    names = ["x02-保守記録.xlsx", "s01-点検票.pdf"]
    text = prior_placeholder(names)
    assert "「x02-保守記録.xlsx」・「s01-点検票.pdf」" in text and PRIOR_NOTE in text
    assert "ほか 2 件" in prior_placeholder([f"d{i}.pdf" for i in range(10)])
    # 引用した文書が無いときは説明だけ。2 件目以降は短い 1 文
    assert PRIOR_NOTE in prior_placeholder([])
    assert prior_placeholder() == PRIOR_TOOL_PLACEHOLDER


def test_cited_documents_only_include_what_the_answer_cited() -> None:
    def tag(n: int, name: str) -> str:
        return f'<資料 n="{n}" 文書="{name}" 見出し="">\n本文\n</資料>'

    msgs: list[Any] = [
        HumanMessage("一つ目"),
        AIMessage(content="", tool_calls=[{"name": "search", "args": {}, "id": "a"}]),
        ToolMessage(content=tag(1, "x02.xlsx") + tag(2, "雑音.pdf") + tag(3, "p01.pptx"), tool_call_id="a"),
        AIMessage(content="答え[3]と[1]"),
        HumanMessage("二つ目"),
        AIMessage(content="資料なしの答え"),
    ]
    assert cited_documents(msgs) == ["p01.pptx", "x02.xlsx"]  # 引用順。検索に出ただけの「雑音.pdf」は入らない
    assert [t.cited for t in turns(msgs)] == [("p01.pptx", "x02.xlsx"), ()]
    assert "（回答が引用した資料: 「p01.pptx」・「x02.xlsx」）" in history_text(msgs)
    # 確定のときに回答へ残した文書名が先（出典番号が検索結果と合わない場合でも使える）
    saved = AIMessage(content="答え[1]", additional_kwargs={"cited_documents": ["x02.xlsx"]})
    assert cited_documents([HumanMessage("q"), saved]) == ["x02.xlsx"]


async def test_finalize_records_cited_documents_on_the_answer() -> None:
    model = FakeToolModel(messages=script(AIMessage(content="停止する[1]。")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    state, _ = await run(agent, ctx(FakeSearch("MX-17 は即時停止を推奨する。")), "MX-17 はどうする？")
    last = state["messages"][-1]
    assert last.additional_kwargs.get("cited_documents") == ["規程.pdf"]


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


class LowSearch(FakeSearch):
    """関連度の低い資料だけを返す検索。"""

    def __init__(self, *texts: str) -> None:
        super().__init__(*texts)
        self.hits = [h.model_copy(update={"score": 0.05}) for h in self.hits]


async def test_no_gap_review_when_first_search_found_nothing_relevant() -> None:
    # 資料に無い質問: 最初の検索が 0 件・関連度が低いなら「見つからない」は正しい答えなので差し戻さない
    for search in (FakeSearch(), LowSearch("無関係な本文")):
        model = FakeToolModel(messages=script(AIMessage(content="資料には記載されていません。")))
        c = ctx(search)
        agent = build_agent(model, checkpointer=InMemorySaver())
        state, _ = await run(agent, c, "社員食堂の営業時間は？")
        assert state["messages"][-1].text == "資料には記載されていません。"
        assert len(model.calls) == 1 and c.stats.gap_reviews == 0
        assert c.primer is not None and c.primer.weak


def test_system_prompt_asks_for_direct_citations_and_one_language() -> None:
    from arag.agent.middleware import system_prompt

    p = system_prompt(ctx(FakeSearch()))
    assert "答えを直接支える資料だけを引用する" in p and "質問の言語だけで書く" in p
    assert "特例" in p  # 特例の規則は残す


# ── 差し戻しは会話ではない・回答の言語（026 T19・T20、hm52・hm60） ──


async def test_send_back_asks_to_rewrite_the_answer_not_to_reply() -> None:
    """差し戻しの依頼には、返事ではなく元の質問への回答を質問の言語で書き直す旨の一文が付く（hm52）。"""
    from arag.agent.middleware import SEND_BACK_TAIL

    model = FakeToolModel(
        messages=script(
            AIMessage(content="P-1042 has 6 in stock [1]."),
            AIMessage(content="P-1042 has 6 in stock [1]."),
        )
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    u = utility('{"kind": "docs", "queries": ["P-1042 在庫"], "table": true}')
    c = ctx(FakeSearch(TABLE), utility_model=u)
    _, custom = await run(agent, c, "How many P-1042 are in stock?")
    retry = model.calls[1][-1]
    assert isinstance(retry, HumanMessage) and retry.text.endswith(SEND_BACK_TAIL)
    # 記録にも同じ依頼を残す
    review = [e["step"] for e in custom if e["type"] == "step" and e["step"]["name"] == "review"][-1]
    assert review["output"]["note"].endswith(SEND_BACK_TAIL)
    assert "利用者の発言ではありません" in SEND_BACK_TAIL and "同じ言語" in SEND_BACK_TAIL


def test_primer_ends_with_answer_language_line() -> None:
    from arag.agent.context import Primer
    from arag.agent.primer import PRIMER_CLOSE, PRIMER_LANGUAGE, with_primer

    out = with_primer("What is X?", Primer(kind="docs", text='<資料 n="1">X は 1</資料>'))
    assert out.endswith(f"{PRIMER_CLOSE}\n{PRIMER_LANGUAGE}")
    assert "上の質問と同じ言語" in PRIMER_LANGUAGE


async def test_low_relevance_note_keeps_question_language() -> None:
    """関連度の低い検索結果の注意書きは、見つからないと質問の言語で答えるよう求める（hm60）。"""
    model = FakeToolModel(messages=script(AIMessage(content="Not found in the documents.")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    await run(agent, ctx(LowSearch("無関係な本文")), "What is the email address?")
    human = next(m for m in model.calls[0] if isinstance(m, HumanMessage))
    assert "見つからなかったと（質問と同じ言語で）答える" in human.text


async def test_sum_from_breakdown_is_not_sent_back_and_is_recorded() -> None:
    """内訳（資料の値）の和は「資料に無い数字」にせず、number_check の derived に残す（T24・hm22）。"""
    answer = "停止時間は合計 135 分です。\n- 30 分 [1]\n- 25 分 [1]\n- 80 分 [1]"
    model = FakeToolModel(messages=script(AIMessage(content=answer)))
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("| 09-02 | PM-04 | 30 |\n| 09-12 | PM-04 | 25 |\n| 09-19 | PM-04 | 80 |"))
    _, custom = await run(agent, c, "PM-04 の停止時間の合計は？")
    assert len(model.calls) == 1 and c.stats.number_reviews == 0
    check = system_steps(custom)["number_check"]
    assert check["output"]["unverified"] == []
    assert check["output"]["derived"] == [{"value": "135", "op": "sum", "from": ["30", "25", "80"]}]
    assert "内訳" in check["summary"]


# ── 空の生成（026 T25、hm58: 思考の記号だけを max_tokens まで出して本文が空） ──


def empty_steps(custom: list[Any]) -> list[dict[str, Any]]:
    return [
        e["step"]
        for e in custom
        if e["type"] == "step"
        and e["step"]["name"] == "system"
        and e["step"]["input"].get("kind") == "empty_generation"
    ]


async def test_empty_generation_is_retried_once() -> None:
    model = FakeToolModel(messages=script(AIMessage(content=""), AIMessage(content="答えは 5 年です[1]")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("保存は 5 年"))
    state, custom = await run(agent, c, "保存期間は？")
    assert state["messages"][-1].text == "答えは 5 年です[1]" and len(model.calls) == 2
    [step] = empty_steps(custom)
    assert step["output"]["result"] == "retried_ok"
    assert {"finish_reason", "reasoning_chars", "tokens_out"} <= set(step["input"])
    assert c.stats.empty_retries == 1 and not c.stats.empty_failed


async def test_empty_after_send_back_uses_the_draft() -> None:
    draft = "変更点はトルク値です[1]。在庫数は資料に記載されていません。"
    model = FakeToolModel(
        messages=script(AIMessage(content=draft), AIMessage(content=""), AIMessage(content=""))
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("HP-300 第3版", "SK-300 在庫"))
    state, custom = await run(agent, c, "第3版の変更点と、関連部品の在庫は？")
    assert state["messages"][-1].text == draft and len(model.calls) == 3
    [step] = empty_steps(custom)
    assert step["output"]["result"] == "used_draft" and step["output"]["pending_review"] == "gap"
    assert not c.stats.empty_failed


async def test_empty_without_draft_ends_as_empty_generation() -> None:
    from arag.agent.runner import _classify

    model = FakeToolModel(messages=script(AIMessage(content=""), AIMessage(content="")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("保存は 5 年"))
    state, custom = await run(agent, c, "保存期間は？")
    assert state["messages"][-1].text == "" and len(model.calls) == 2
    [step] = empty_steps(custom)
    assert step["output"]["result"] == "failed" and step["input"]["retried"] is True
    assert c.stats.empty_failed and _classify("", c) == "empty_generation"


async def test_empty_generation_is_retried_only_once_per_run() -> None:
    model = FakeToolModel(
        messages=script(AIMessage(content=""), tool_call("search", query="保存期間"), AIMessage(content=""))
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("保存は 5 年"))
    _, custom = await run(agent, c, "保存期間は？")
    assert len(model.calls) == 3  # 2 度目の空はやり直さない
    assert [s["output"]["result"] for s in empty_steps(custom)] == ["retried_ok", "failed"]
    assert empty_steps(custom)[1]["input"]["retried"] is False


def test_send_back_tail_asks_to_call_the_tool_first() -> None:
    """ツールを求める差し戻しで、暗算で数字だけ書き換えず、まずそのツールを呼ばせる（026 T26）。"""
    from arag.agent.middleware import SEND_BACK_TAIL

    assert "まずそのツールを呼んで" in SEND_BACK_TAIL and "暗算" in SEND_BACK_TAIL


# ── 差し戻しへの返事を回答にしない（specs/026 T29） ──


def discarded_steps(custom: list[Any]) -> list[dict[str, Any]]:
    return [
        e["step"]
        for e in custom
        if e["type"] == "step"
        and e["step"]["name"] == "system"
        and e["step"]["input"].get("kind") == "rewrite_discarded"
        and e["step"]["status"] == "done"
    ]


TABLE_DRAFT = "| 項目 | HP-300 | HP-320 |\n|---|---|---|\n| 在庫 | 6 [1] | 4 [1] |"


async def table_send_back(redo: AIMessage, *rest: AIMessage) -> tuple[dict[str, Any], list[Any], RunContext]:
    model = FakeToolModel(messages=script(AIMessage(content=TABLE_DRAFT), redo, *rest))
    agent = build_agent(model, checkpointer=InMemorySaver())
    u = utility('{"kind": "docs", "queries": ["在庫が発注点を下回る部品"], "table": true}')
    c = ctx(FakeSearch(TABLE), utility_model=u)
    state, custom = await run(agent, c, "在庫が発注点を下回る部品は？")
    return state, custom, c


async def test_rewrite_without_citations_falls_back_to_the_draft() -> None:
    state, custom, _ = await table_send_back(AIMessage(content="P-1042 が該当します。"))
    assert state["messages"][-1].text == TABLE_DRAFT
    [step] = discarded_steps(custom)
    assert step["input"]["reason"] == "no_citations" and step["input"]["review"] == "table"
    assert step["output"]["used"] == "draft" and step["output"]["pending_review"] == "table"
    assert step["output"]["discarded"] == "P-1042 が該当します。"


async def test_reply_to_the_send_back_falls_back_to_the_draft() -> None:
    """3100: 表の集計の確認で差し戻すと「了解いたしました。指示に従い…」が回答になった。"""
    reply = "了解いたしました。指示に従い、table_query を使用して回答します[1]。"
    state, custom, _ = await table_send_back(AIMessage(content=reply))
    assert state["messages"][-1].text == TABLE_DRAFT
    [step] = discarded_steps(custom)
    assert step["input"]["reason"] == "reply_to_request"
    # 下書きに戻しても数字の照合は行う（未確認の数字は既存の注意で示す）
    assert "number_check" in system_steps(custom)


async def test_rewrite_after_calling_a_tool_is_kept() -> None:
    state, custom, _ = await table_send_back(
        tool_call("table_query", source="1", where="在庫 < 発注点"),
        AIMessage(content="了解しました。P-1042 です。"),
    )
    assert state["messages"][-1].text == "了解しました。P-1042 です。"
    assert discarded_steps(custom) == []


async def test_draft_without_citations_does_not_use_the_citation_rule() -> None:
    model = FakeToolModel(
        messages=script(
            AIMessage(content="資料に記載されていません。"),
            AIMessage(content="SK-300 の在庫は 6 個です。"),
        )
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    state, custom = await run(agent, ctx(FakeSearch("SK-300 在庫 6")), "SK-300 の在庫は？")
    assert state["messages"][-1].text == "SK-300 の在庫は 6 個です。"
    assert discarded_steps(custom) == []


# ── 引用の刈り込み（specs/026 T31） ──


async def test_citations_without_the_value_are_pruned_and_recorded() -> None:
    model = FakeToolModel(messages=script(AIMessage(content="締付トルクは 52 N·m です[1][2]。")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("締付トルクは 52 N·m とする。", "品質会議で締付トルクの見直しを決めた。"))
    state, custom = await run(agent, c, "締付トルクは？")
    assert state["messages"][-1].text == "締付トルクは 52 N·m です[1]。"
    step = system_steps(custom)["citation_pruned"]
    assert step["label"] == "引用の刈り込み"
    # 番号は検索で振った番号で、保存のときに振り直されるので、資料の名前も添えて後から追えるようにする
    assert step["output"]["pruned"] == [
        {
            "sentence": "締付トルクは 52 N·m です[1][2]。",
            "removed": [2],
            "kept": [1],
            "values": ["52"],
            "ignored": [],
            "documents": {"1": "規程.pdf", "2": "規程.pdf"},
        }
    ]
    # 刈り込みで短くなった分を「末尾の言い直し」に数えない
    assert system_steps(custom)["citation_cleanup"]["output"]["tail_dropped_chars"] == 0


async def test_pruning_can_be_turned_off() -> None:
    model = FakeToolModel(messages=script(AIMessage(content="締付トルクは 52 N·m です[1][2]。")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("締付トルクは 52 N·m とする。", "品質会議で決めた。"), citation_prune=False)
    state, custom = await run(agent, c, "締付トルクは？")
    assert state["messages"][-1].text == "締付トルクは 52 N·m です[1][2]。"
    assert "citation_pruned" not in system_steps(custom)


async def test_pruning_ignores_values_from_the_users_question() -> None:
    # 質問の型番（HP-300）はどの資料にもあるので判断に使わない。画像の説明は質問に含めない（T34）
    model = FakeToolModel(messages=script(AIMessage(content="HP-300 の締付トルクは 52 N·m です[1][2]。")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("HP-300 の締付トルクは 52 N·m とする。", "HP-300 の品質会議で見直しを決めた。"))
    c.user_question = "HP-300 の締付トルクは？"
    state, custom = await run(agent, c, "HP-300 の締付トルクは？")
    assert state["messages"][-1].text == "HP-300 の締付トルクは 52 N·m です[1]。"
    [p] = system_steps(custom)["citation_pruned"]["output"]["pruned"]
    assert p["values"] == ["52"] and p["ignored"] == ["300", "HP-300"]


async def test_query_almost_same_as_question_is_skipped_and_recorded() -> None:
    model = FakeToolModel(messages=script(AIMessage(content="答え[1]")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    search = FakeSearch("停止は 2.25 時間。")
    q = "9月の冷却水ポンプ PM-04 の保守による停止時間は合計何時間ですか？"
    u = utility(
        '{"kind": "docs", "queries": ["9月の冷却水ポンプ PM-04 の保守による停止時間の合計"], "table": false}'
    )
    c = ctx(search, utility_model=u)
    _, custom = await run(agent, c, q)
    # 質問文での検索だけ行い、省いたことは「システムの処理」に残す
    assert [r.query for r in search.requests] == [q]
    sys = [e["step"] for e in custom if e["type"] == "step" and e["step"]["name"] == "system"]
    skipped = next(s for s in sys if s["input"]["kind"] == "query_skipped")
    assert skipped["output"]["skipped_queries"] == ["9月の冷却水ポンプ PM-04 の保守による停止時間の合計"]


def test_similarity_and_distinct_part() -> None:
    from arag.agent.primer import distinct_part, similarity

    assert similarity("第2版 締付トルク", "第2版と第3版のトルクの違いは？") < 0.85
    assert similarity("PM-04 停止時間", "PM-04　停止時間") == 1.0
    q = "9月の冷却水ポンプ PM-04 の保守による停止時間は合計何時間ですか？"
    assert distinct_part("9月の冷却水ポンプ PM-04 の保守による停止時間の合計", q).startswith("…")
    assert distinct_part("全然ちがう", q) == "全然ちがう"


async def test_refers_prior_scopes_the_search_to_previously_cited_documents() -> None:
    from .agent_fakes import DOC

    model = FakeToolModel(messages=script(AIMessage(content="一回目[1]"), AIMessage(content="二回目[1]")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    search = FakeSearch("担当は小野寺。")
    u = utility(
        '{"kind": "docs", "queries": ["PM-04 停止時間"], "table": false}',
        '{"kind": "docs", "queries": ["担当者"], "table": false, "refers_prior": true}',
    )
    await run(agent, ctx(search, utility_model=u), "PM-04 の停止時間は？", thread="s1")
    _, custom = await run(agent, ctx(search, utility_model=u), "その資料に担当者は？", thread="s1")
    # 前のターンが引用した文書（規程.pdf）に絞って検索し、その記録を残す
    scopes = [r.document_ids for r in search.requests[1:]]
    assert [DOC] in scopes  # 絞った検索
    assert None in scopes  # 「新版と比べて」のように他の文書も要るときのため、絞らない検索も足す
    sys = [e["step"] for e in custom if e["type"] == "step" and e["step"]["name"] == "system"]
    scope = next(s for s in sys if s["input"]["kind"] == "scope_prior")
    assert scope["output"]["documents"] == ["規程.pdf"]
    assert any(
        e["step"]["input"].get("scope_documents") == ["規程.pdf"] for e in custom if e["type"] == "step"
    )


async def test_refers_prior_is_ignored_without_cited_documents() -> None:
    model = FakeToolModel(messages=script(AIMessage(content="一回目"), AIMessage(content="二回目")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    search = FakeSearch("本文")
    u = utility(
        '{"kind": "docs", "queries": ["a"], "table": false}',
        '{"kind": "docs", "queries": ["b"], "table": false, "refers_prior": true}',
    )
    await run(agent, ctx(search, utility_model=u), "最初の質問", thread="s2")
    await run(agent, ctx(search, utility_model=u), "その資料は？", thread="s2")
    assert all(r.document_ids is None for r in search.requests)


def test_is_announce_only() -> None:
    assert is_announce_only("まずは文書の章立てを取得します。")
    assert is_announce_only("担当者を確認します。")
    # 事実を述べた回答・引用のある回答・長い回答は予告ではない
    assert not is_announce_only("異常時は即時停止します。")
    assert not is_announce_only("まず点検してから停止します[1]。")
    assert not is_announce_only("担当者は小野寺です。")
    assert not is_announce_only("あ" * 200 + "確認します。")
    assert not is_announce_only("")


async def test_announce_only_answer_is_retried_once_with_a_request_to_call_tools() -> None:
    model = FakeToolModel(
        messages=script(
            AIMessage(content="まずは文書の章立てを取得します。"), AIMessage(content="停止する[1]。")
        )
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    state, custom = await run(agent, ctx(FakeSearch("MX-17 は即時停止を推奨する。")), "MX-17 はどうする？")
    # 予告は回答として残らず、2 回目の呼び出しにだけ予告と依頼が添えられる
    assert state["messages"][-1].text == "停止する[1]。"
    assert not any("取得します" in m.text for m in state["messages"])
    assert len(model.calls) == 2
    assert any(isinstance(m, HumanMessage) and m.text == ANNOUNCE_NOTE for m in model.calls[1])
    sys = [e["step"] for e in custom if e["type"] == "step" and e["step"]["name"] == "system"]
    assert any(s["input"]["kind"] == "announce_only" for s in sys)


async def test_announce_only_is_retried_only_once() -> None:
    model = FakeToolModel(
        messages=script(AIMessage(content="まず確認します。"), AIMessage(content="次に取得します。"))
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    state, _ = await run(agent, ctx(FakeSearch("本文")), "質問")
    assert len(model.calls) == 2 and state["messages"][-1].text == "次に取得します。"


def test_guard_refers_needs_a_demonstrative_and_a_document_word() -> None:
    from arag.agent.primer import strip_documents
    from arag.agent.understand import Understanding, guard_refers

    u = Understanding(refers_prior=True)
    assert guard_refers(u, "その資料に担当者は書いてありますか？").refers_prior
    assert guard_refers(u, "さっきの手順書で 9月19日の作業は？").refers_prior
    assert guard_refers(u, "Is it in that document?").refers_prior
    # 話題の続き（旧版・それ・そこ）は前の文書を指さない
    g = guard_refers(u, "旧版ではいくつでしたか？")
    assert not g.refers_prior and g.refers_overridden
    assert not guard_refers(u, "そこのリードタイムは？").refers_prior
    assert not guard_refers(Understanding(), "その資料は？").refers_overridden
    # 絞ったときは、検索語から文書名を外す
    assert strip_documents("x02-保守記録_2026-09.xlsx 担当者", ["x02-保守記録_2026-09.xlsx"]) == "担当者"
    assert (
        strip_documents("x02-保守記録_2026-09.xlsx", ["x02-保守記録_2026-09.xlsx"])
        == "x02-保守記録_2026-09.xlsx"
    )


def test_named_document_refs() -> None:
    from arag.agent.ops import named_document_refs

    assert named_document_refs("p03-新人安全教育.pptx 总结一下这篇文章讲了啥") == ["p03-新人安全教育.pptx"]
    assert named_document_refs("x02-保守記録_2026-09.xlsx を全部読んで") == ["x02-保守記録_2026-09.xlsx"]
    assert named_document_refs("w03-HP-300分解手順書_第3版 の最後の節は？") == ["w03-HP-300分解手順書_第3版"]
    # 文書名でないものは拾わない
    assert named_document_refs("HP-300 の締付トルクはいくつですか？") == []
    assert named_document_refs("9月の PM-04 の停止時間は？") == []


def test_record_system_carries_only_measured_durations() -> None:
    from arag.agent.steps import elapsed_ms, record_system

    got: list[dict[str, Any]] = []
    record_system(got.append, "a", "k", "測った処理", "x", duration_ms=elapsed_ms(0.0))
    record_system(got.append, "b", "k", "記録だけ", "y")
    assert got[0]["step"]["duration_ms"] >= 1  # 測った処理は 0 にならない
    assert got[1]["step"]["duration_ms"] == 0  # 測っていない処理は 0（画面は時間を出さない）


async def test_each_model_call_is_recorded_with_its_time() -> None:
    """モデルの応答（回答を書く・ツールを選ぶ）の時間も記録する。

    経路の段階の時間が合計と合う（specs/029 T35）。
    """
    model = FakeToolModel(
        messages=script(
            AIMessage(content="", tool_calls=[{"name": "search", "args": {"query": "MX-17"}, "id": "a"}]),
            AIMessage(content="停止する[1]。"),
        )
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    _, custom = await run(agent, ctx(FakeSearch("MX-17 は即時停止を推奨する。")), "MX-17 はどうする？")
    calls = [
        e["step"] for e in custom if e["type"] == "step" and e["step"]["input"].get("kind") == "model_call"
    ]
    assert len(calls) == 2
    # 時間は測ったもの（1 以上）。節点の名前は runner が付ける
    assert all(isinstance(c["duration_ms"], int) and c["duration_ms"] >= 1 for c in calls)
    assert calls[0]["output"]["chose"] == ["search"]
    assert calls[0]["summary"] == "ツールを選んだ: 検索「MX-17」"
    # モデルが呼んだ検索も、何を探したかを要約に出す（システムの検索と同じ形）
    done = [e["step"] for e in custom if e["type"] == "step" and e["step"]["status"] == "done"]
    search = next(s for s in done if s["name"] == "search" and s["input"].get("by") != "system")
    assert search["summary"].startswith("「MX-17」・資料")
    assert calls[1]["output"]["chose"] == []
    assert calls[0]["id"] != calls[1]["id"]


async def test_guard_records_when_it_lets_the_answer_through() -> None:
    """見張りが何もせず通したときも記録に残す（確認の通過と同じ。specs/029 T41）。"""
    model = FakeToolModel(messages=script(AIMessage(content="停止する[1]。")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    _, custom = await run(agent, ctx(FakeSearch("MX-17 は即時停止を推奨する。")), "MX-17 はどうする？")
    passed = [
        e["step"] for e in custom if e["type"] == "step" and e["step"]["input"].get("kind") == "guard_passed"
    ]
    assert len(passed) == 1
    assert passed[0]["label"] == "見張りの通過"
    assert passed[0]["input"]["checks"] == ["empty", "announce_only"]


# ── 省略の読み残し・同じ呼び出しの繰り返し・聞き返し（specs/031） ──


def test_omitted_outline_with_unknown_answer_is_sent_back() -> None:
    from arag.agent.middleware import pick_review
    from arag.agent.ops import OUTLINE_OMITTED

    c = ctx(FakeSearch("本文"))
    outline = ToolMessage(
        content=f"「a.pdf」の章立て（643 節）\n- 1. 序\n{_omitted_line(OUTLINE_OMITTED)}\n- 643. 用語集",
        tool_call_id="x",
        name="get_outline",
    )
    turn = [HumanMessage("最後の章は？"), tool_call("get_outline", document="a.pdf"), outline]
    draft = "末尾は「…ほか 443 節」と省略されており、お答えすることができません。"
    found = pick_review(c, turn, draft, 2, True)
    assert found is not None and found.kind == "omitted" and "start" in found.note
    # 省略が無ければ、この種類の差し戻しはしない（調べ残しの見直しに回る）
    plain = ToolMessage(content="「a.pdf」の章立て（2 節）", tool_call_id="x", name="get_outline")
    other = pick_review(c, [turn[0], turn[1], plain], "特定できません。", 2, True)
    assert other is None or other.kind != "omitted"
    # ターンに 1 度まで
    again = pick_review(c, turn, "お答えすることができません。", 2, True, done=["omitted", "gap"])
    assert again is None


def _omitted_line(mark: str) -> str:
    return f"{mark}第 2〜642 節は未表示。読むには get_outline に start=2 を渡す）"


async def test_repeated_identical_tool_call_is_skipped_and_recorded() -> None:
    model = FakeToolModel(
        messages=script(
            tool_call("calculate", expression="1 + 2"),
            tool_call("calculate", expression="1 + 2"),
            AIMessage(content="3 です[1]"),
        )
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("本文"))
    state, custom = await run(agent, c, "1 + 2 は？")
    calcs = [s for s in own_steps(custom) if s["status"] == "done"]
    assert [s["summary"] for s in calcs] == ["1 + 2 = 3", "同じ呼び出しの繰り返しのため実行しなかった"]
    assert calcs[1]["output"] == {"skipped": "duplicate"}
    tools = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    assert "既に呼んでいます" in tools[1].text and c.stats.tool_calls == 1
    # 次のターンでは同じ呼び出しをし直せる
    model2 = FakeToolModel(
        messages=script(tool_call("calculate", expression="1 + 2"), AIMessage(content="3"))
    )
    agent2 = build_agent(model2, checkpointer=InMemorySaver())
    await run(agent2, c, "もう一度")
    assert c.stats.tool_calls == 2


async def test_ask_user_ends_the_turn_with_the_question_and_options() -> None:
    from arag.agent.context import Completion, RunHooks

    got: list[Completion] = []

    async def completed(x: Completion) -> None:
        got.append(x)

    made: list[int] = []

    async def followups() -> list[str]:
        made.append(1)
        return []

    model = FakeToolModel(
        messages=script(
            tool_call(
                "ask_user",
                question="どちらの文書のことですか？",
                options=["第2版の手順書について", "第3版の手順書について", "第3版の手順書について"],
            ),
            AIMessage(content="第3版は 52 N·m です[1]"),
        )
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("第3版 52 N·m"))
    c.hooks = RunHooks(completed=completed, followups=followups)
    state, custom = await run(agent, c, "手順書のトルクは？")
    last = state["messages"][-1]
    assert isinstance(last, AIMessage) and last.text == "どちらの文書のことですか？"
    assert last.additional_kwargs["clarify"] is True
    assert len(got) == 1 and got[0].answer == "どちらの文書のことですか？" and got[0].reason is None
    assert got[0].suggestions == ["第2版の手順書について", "第3版の手順書について"] and not got[0].followups
    steps = [e["step"] for e in custom if e["type"] == "step"]
    assert any(s["name"] == "ask_user" and s["status"] == "done" for s in steps)
    assert any(s["name"] == "system" and s["input"].get("kind") == "clarify" for s in steps)
    # 見張りが聞き返しで確定へ回したことも記録する（029 T42）。通過の記録は出さない
    kinds = [s["input"].get("kind") for s in steps if s["name"] == "system"]
    assert "guard_clarify" in kinds and "guard_passed" not in kinds
    assert not any(s["name"] == "review" for s in steps) and len(model.calls) == 1
    assert not made  # 聞き返しでは続けて聞く候補を作らない
    # 次のターンでは聞き返しを外して答えさせ、外したことを記録に残す
    got.clear()
    _, custom2 = await run(agent, c, "第3版の手順書について")
    assert model.tool_counts[-1] == 8
    assert any(
        e["step"]["name"] == "system" and e["step"]["input"].get("kind") == "ask_user_blocked"
        for e in custom2
        if e["type"] == "step"
    )
    assert got[0].answer == "第3版は 52 N·m です[1]"


async def test_reason_not_written_in_the_cited_material_is_sent_back() -> None:
    model = FakeToolModel(
        messages=script(
            AIMessage(content="KG-2 は漏れ対策のため廃止予定です[1]。"),
            AIMessage(content="廃止予定の理由は資料に書かれていません。台帳では KG-2 は廃止予定です[1]。"),
        )
    )
    u = utility(
        '{"kind": "docs", "queries": ["KG-2 廃止予定 理由"], "table": false}',
        '{"supported": false, "why": "資料はグリスの変更の理由を述べ、KG-2 の廃止の理由は書いていない"}',
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("第3版: 漏れ対策としてグリスを KG-5 に変更した。"), utility_model=u)
    state, custom = await run(agent, c, "KG-2 はなぜ廃止予定なのですか？")
    assert state["messages"][-1].text.startswith("廃止予定の理由は資料に書かれていません")
    steps = [e["step"] for e in custom if e["type"] == "step"]
    check = [s for s in steps if s["name"] == "system" and s["input"].get("kind") == "reason_check"]
    first = next(s for s in check if s["id"] == "system-reason-check")
    assert first["output"]["supported"] is False and first["input"]["cited"] == [1]
    # 書き直しも確かめ直す（台本が尽きて判定できなければ、注記は付けない）
    assert any(s["id"] == "system-reason-recheck" for s in check)
    review = [s for s in steps if s["name"] == "review" and s["status"] == "done"]
    assert review[-1]["input"]["kind"] == "reason" and "推測と明記" in review[-1]["output"]["note"]
    assert c.stats.reason_reviews == 1 and len(model.calls) == 2


async def test_reason_check_runs_only_for_why_questions_and_is_recorded_when_supported() -> None:
    model = FakeToolModel(messages=script(AIMessage(content="漏れ対策のためです[1]。")))
    u = utility(
        '{"kind": "docs", "queries": ["トルク 変更 理由"], "table": false}',
        '{"supported": true, "why": "資料に漏れ対策として変更したとある"}',
    )
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("漏れ対策として締付トルクを 52 N·m に上げた。"), utility_model=u)
    _, custom = await run(agent, c, "トルクを変えた理由は？")
    kinds = [
        e["step"]["input"].get("kind")
        for e in custom
        if e["type"] == "step" and e["step"]["name"] == "system"
    ]
    assert "reason_check" in kinds and c.stats.reason_reviews == 0 and len(model.calls) == 1
    # 理由を尋ねない質問では呼ばない（台本の 2 つ目が残る）
    from arag.agent.reason_check import asks_reason

    assert asks_reason("Why was KG-2 discontinued?") and not asks_reason("KG-2 の単価は？")


def test_reason_check_needs_both_the_subject_and_the_link() -> None:
    from arag.agent.reason_check import parse

    linked = parse(
        '{"subject": "KG-2 の廃止", "subject_in_material": true, "reason_linked": true, "why": "a"}'
    )
    assert linked.supported is True and linked.why == "KG-2 の廃止: a"
    stitched = parse('{"subject": "KG-2 の廃止", "subject_in_material": false, "reason_linked": true}')
    assert stitched.supported is False
    assert parse("判定できません").supported is None
    assert parse('{"subject": "x"}').supported is None


async def test_rewrite_still_without_support_gets_a_caveat() -> None:
    from arag.agent.middleware import REASON_CAVEAT

    model = FakeToolModel(
        messages=script(
            AIMessage(content="KG-2 は漏れ対策のため廃止予定です[1]。"),
            AIMessage(content="KG-2 は漏れ対策のため廃止予定です[1]。"),
        )
    )
    no = '{"subject": "KG-2 の廃止", "subject_in_material": false, "reason_linked": false}'
    u = utility('{"kind": "docs", "queries": ["KG-2 廃止 理由"], "table": false}', no, no)
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("第3版: 漏れ対策としてグリスを KG-5 に変更した。"), utility_model=u)
    state, custom = await run(agent, c, "KG-2 はなぜ廃止予定なのですか？")
    assert state["messages"][-1].text == f"KG-2 は漏れ対策のため廃止予定です[1]。\n\n{REASON_CAVEAT}"
    kinds = [
        e["step"]["input"].get("kind")
        for e in custom
        if e["type"] == "step" and e["step"]["name"] == "system"
    ]
    assert kinds.count("reason_check") == 2 and "reason_caveat" in kinds


async def test_this_document_without_a_document_is_asked_back_with_found_documents() -> None:
    from arag.agent.context import Completion, RunHooks

    from .agent_fakes import fake_hit

    got: list[Completion] = []

    async def completed(x: Completion) -> None:
        got.append(x)

    model = FakeToolModel(messages=script(AIMessage(content="要点です[1]")))
    search = FakeSearch()
    search.hits = [
        fake_hit("本文 A").model_copy(update={"document_name": "a.pdf"}),
        fake_hit("本文 B").model_copy(update={"document_name": "b.docx"}),
        fake_hit("本文 A2").model_copy(update={"document_name": "a.pdf"}),
    ]
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(search)
    c.hooks = RunHooks(completed=completed)
    state, custom = await run(agent, c, "この資料の要点を3つにまとめて")
    # モデルを呼ばずに聞き返す。選択肢は見つかった文書の名前を添えた質問
    assert len(model.calls) == 0 and got[0].answer.startswith("どの資料についてですか")
    assert got[0].suggestions == [
        "a.pdf この資料の要点を3つにまとめて",
        "b.docx この資料の要点を3つにまとめて",
    ]
    assert state["messages"][-1].additional_kwargs["clarify"] is True
    step = next(
        e["step"] for e in custom if e["type"] == "step" and e["step"]["input"].get("kind") == "clarify"
    )
    assert step["input"]["reason"] == "document_unspecified"
    # 続けては聞き返さない（前のターンが聞き返し）
    got.clear()
    await run(agent, c, "この資料の要点は？")
    assert got[0].answer == "要点です[1]"


def test_document_unspecified_conditions() -> None:
    import uuid as _uuid

    from arag.agent.primer import document_unspecified

    c = ctx(FakeSearch())
    assert document_unspecified(c, "この資料の要点は？", [])
    assert not document_unspecified(c, "この手順書の締付トルクは？", [])
    assert not document_unspecified(c, "HP-300 の締付トルクは？", [])
    scoped = ctx(FakeSearch(), document_ids=[_uuid.uuid4()])
    assert not document_unspecified(scoped, "この資料の要点は？", [])


def test_clarify_options_put_recent_documents_first_and_drop_weak_hits() -> None:
    from arag.agent.primer import clarify_options

    from .agent_fakes import fake_hit

    c = ctx(FakeSearch())
    for name, score in [("a.pdf", 0.9), ("b.md", 0.3), ("c.docx", 0.6)]:
        c.registry.add_hit(fake_hit(name).model_copy(update={"document_name": name, "score": score}))
    got = clarify_options(c, "この資料の要点は？", ["mine.pdf"])
    # 最近の文書が先。b.md（0.3 < 0.9 の半分）は外す
    assert got == ["mine.pdf この資料の要点は？", "a.pdf この資料の要点は？", "c.docx この資料の要点は？"]


def test_clarify_options_skip_unrelated_recent_documents_when_the_question_has_content() -> None:
    """内容の語（締付トルクなど）がある質問では、検索で関連の無い最近の文書を候補に入れない（031 T13）。"""
    from arag.agent.primer import clarify_options, has_content_terms

    from .agent_fakes import fake_hit

    c = ctx(FakeSearch())
    for name, score in [("w03.docx", 0.9), ("w02.docx", 0.8), ("notes.pdf", 0.2)]:
        c.registry.add_hit(fake_hit(name).model_copy(update={"document_name": name, "score": score}))
    got = clarify_options(c, "この資料の締付トルクはいくつですか？", ["handbook.pdf", "w02.docx"])
    assert [g.split(" ")[0] for g in got] == ["w02.docx", "w03.docx"]
    assert has_content_terms("この資料の締付トルクはいくつですか？")
    assert not has_content_terms("この資料の要点を3つにまとめて")
    assert not has_content_terms("Summarize this document")


def test_document_unspecified_covers_attached_tables_and_english() -> None:
    """添付・表・本資料・英語の言い方も、指す文書が決まらなければ聞き返す（specs/031 T14）。"""
    from arag.agent.primer import document_unspecified

    c = ctx(FakeSearch())
    for q in [
        "添付の資料の要点を3つにまとめてください。",
        "添付したファイルの内容を教えて",
        "この表の合計金額はいくらですか？",
        "このスライドの結論は？",
        "本資料の改訂日は？",
        "Summarize the attached file.",
        "What is the total in this spreadsheet?",
    ]:
        assert document_unspecified(c, q, []), q
    # 種類の語（手順書・仕様書）は対象にしない。「表計算」「図面」のような語の一部も
    for q in ["この手順書の締付トルクは？", "価格表の合計は？", "部品台帳の表の見方は？"]:
        assert not document_unspecified(c, q, []), q


def test_reference_unknown_only_without_history() -> None:
    """初めのターンの「この件」「それは」は指す先が無い（specs/031 T14）。前のターンがあれば決まる。"""
    from langchain_core.messages import HumanMessage

    from arag.agent.primer import reference_unknown

    for q in [
        "この件の担当者は誰ですか？",
        "それはいつまでに対応する必要がありますか？",
        "あの件はどうなりましたか",
        "例の件の期限は？",
    ]:
        assert reference_unknown(q, []), q
    for q in [
        "それぞれの担当者は誰ですか？",
        "これまでの不良率の推移は？",
        "HP-300 の件の担当者は？",
        "その後の対応は？",
    ]:
        assert not reference_unknown(q, []), q
    history = [HumanMessage(content="シールキットの補充は誰が担当？"), AIMessage(content="佐伯さんです[1]")]
    assert not reference_unknown("それはいつまでに行いますか？", history)


async def test_reference_unknown_is_asked_back_without_options() -> None:
    from arag.agent.context import Completion, RunHooks

    got: list[Completion] = []

    async def completed(x: Completion) -> None:
        got.append(x)

    model = FakeToolModel(messages=script(AIMessage(content="担当は佐伯です[1]")))
    agent = build_agent(model, checkpointer=InMemorySaver())
    c = ctx(FakeSearch("担当 佐伯"))
    c.hooks = RunHooks(completed=completed)
    _, custom = await run(agent, c, "この件の担当者は誰ですか？")
    # 検索の結果は当てにならないので選択肢は出さず、対象を添えて聞き直してもらう
    assert len(model.calls) == 0 and "「この件」" in got[0].answer and got[0].suggestions == []
    step = next(
        e["step"] for e in custom if e["type"] == "step" and e["step"]["input"].get("kind") == "clarify"
    )
    assert step["input"]["reason"] == "reference_unknown"


def test_clarify_options_fill_up_to_two_when_the_question_names_no_document() -> None:
    """関連の高い文書が 1 つだけでも、「その文書」は決まらないので次に高い文書で 2 つにする（T14）。"""
    from arag.agent.primer import clarify_options

    from .agent_fakes import fake_hit

    c = ctx(FakeSearch())
    for name, score in [("w01.docx", 0.9), ("d01.pdf", 0.3), ("x03.xlsx", 0.2)]:
        c.registry.add_hit(fake_hit(name).model_copy(update={"document_name": name, "score": score}))
    got = clarify_options(c, "その文書の改訂日はいつですか？", [])
    assert [g.split(" ")[0] for g in got] == ["w01.docx", "d01.pdf"]
