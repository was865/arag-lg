"""社内システム（MCP）のツールをエージェントが使う流れ（偽モデル。specs/032 R12〜R25）。"""

import re
import uuid
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from arag.agent.config import AgentCfg
from arag.agent.context import McpRun
from arag.agent.graph import build_agent
from arag.agent.mcp_tools import build_tool
from arag.mcp.client import Caller
from arag.mcp.registry import ServerSpec, ToolSpec

from .agent_fakes import FakeSearch, FakeToolModel, script, tool_call
from .mcp_fake import KEY, running
from .test_agent_graph import ctx, run, utility

SCHEMA = {"type": "object", "properties": {"part": {"type": "string"}}, "required": ["part"]}


def spec(url: str, timeout: float | None = None) -> ToolSpec:
    srv = ServerSpec(
        uuid.uuid4(), "erp", "ERP（資材・購買）", url, "identity", None, timeout, "部品・在庫・発注"
    )
    return ToolSpec(srv, "get_stock", "部品の現在の在庫", SCHEMA)


def mcp_run(t: ToolSpec, *, usable: bool = True, max_calls: int = 6, max_rows: int = 50) -> McpRun:
    m = McpRun(
        caller=Caller("u", ("製造課",)),
        identity_key=KEY,
        box=None,
        timeout_sec=5,
        max_calls=max_calls,
        max_rows=max_rows,
        max_chars=8000,
    )
    if usable:
        m.usable = {t.agent_name: t}
    else:
        m.removed = {"erp": ("mcp_filtered", t.server.label, "この利用者の部門は使える範囲に入っていない")}
    return m


def systems(custom: list[Any]) -> dict[str, dict[str, Any]]:
    return {
        e["step"]["input"]["kind"]: e["step"]
        for e in custom
        if e["type"] == "step" and e["step"]["name"] == "system"
    }


def systems_all(custom: list[Any], kind: str) -> list[dict[str, Any]]:
    return [
        e["step"]
        for e in custom
        if e["type"] == "step" and e["step"]["name"] == "system" and e["step"]["input"].get("kind") == kind
    ]


def steps_of(custom: list[Any], name: str) -> list[dict[str, Any]]:
    return [e["step"] for e in custom if e["type"] == "step" and e["step"]["name"] == name]


async def test_calls_system_and_cites_it_with_time() -> None:
    with running() as (url, _):
        t = spec(url)
        model = FakeToolModel(
            messages=script(tool_call(t.agent_name, part="P-1042"), AIMessage(content="今は 15 個です[2]。"))
        )
        agent = build_agent(model, checkpointer=InMemorySaver(), extra_tools=[build_tool(t)])
        c = ctx(FakeSearch("部品台帳（9月30日現在）: SK-300 の在庫 6"), mcp=mcp_run(t))
        state, custom = await run(agent, c, "SK-300 の在庫は今いくつ？")
    # 社内システムの結果は資料タグで届き、番号で引用できる
    cited = c.registry.get(2)
    assert cited is not None and cited.kind == "system" and cited.block_type == "record"
    assert cited.record and cited.record["rows"] == [["P-1042", 15, 10]] and cited.record["fetched_at"]
    assert cited.record["args"] == {"part": "P-1042"}
    tool_msg = state["messages"][-2]
    assert '種類="社内システム"' in tool_msg.text and "| P-1042 | 15 | 10 |" in tool_msg.text
    # 身元は利用者のもの（R13）
    assert c.mcp is not None and c.mcp.calls == 1
    # 記録: 社内システムのステップ（表示名・行数）
    step = steps_of(custom, t.agent_name)[-1]
    assert step["label"] == "社内システム: ERP（資材・購買）"
    # 終わったら件数と所要時間（specs/033 R18）。問い合わせ中はツールと引数
    assert re.fullmatch(r"ERP（資材・購買）・1 行・\d+\.\d 秒", step["summary"])
    started = next(s for s in steps_of(custom, t.agent_name) if s["status"] == "running")
    assert started["summary"] == "ERP（資材・購買） に問い合わせ中: get_stock part=P-1042"
    assert step["output"]["columns"] == ["部品番号", "現在庫", "発注点"]
    # 技術者が確かめられる呼び出しの中身（specs/036 R1・R2・R7・R8）
    out = step["output"]
    assert out["server"] == "erp" and out["tool"] == "get_stock" and out["args"] == {"part": "P-1042"}
    assert isinstance(out["rtt_ms"], int) and out["rtt_ms"] >= 0
    assert out["result"] == tool_msg.text  # モデルに渡した文そのもの
    # プロンプト: 使えるシステムがあるターンだけ社内システムの節を足す
    sys = model.calls[0][0]
    assert isinstance(sys, SystemMessage) and "社内の文書と社内システムの結果だけを根拠に" in sys.text
    assert "ERP（資材・購買）" in sys.text
    # 出典パネル: 社内システムの印と表
    _, sources = c.registry.sources()
    src = next(s for s in sources if s.get("kind") == "system")
    assert src["title"] == "ERP（資材・購買）" and src["sections"][0]["record"]["total"] == 1


async def test_filtered_server_is_removed_and_recorded() -> None:
    with running() as (url, _):
        t = spec(url)
        model = FakeToolModel(messages=script(AIMessage(content="文書では 6 個です[1]。")))
        agent = build_agent(model, checkpointer=InMemorySaver(), extra_tools=[build_tool(t)])
        c = ctx(FakeSearch("在庫 6"), mcp=mcp_run(t, usable=False))
        _, custom = await run(agent, c, "SK-300 の在庫は？")
    assert t.agent_name not in model.tool_names[0] and "search" in model.tool_names[0]
    rec = systems(custom)["mcp_filtered"]
    assert rec["input"]["server"] == "erp" and "使える範囲" in rec["summary"]
    # 使えるシステムが無ければプロンプトは今までどおり
    assert "社内の文書だけを根拠に" in model.calls[0][0].text


async def test_no_mcp_state_hides_system_tools() -> None:
    with running() as (url, _):
        t = spec(url)
        model = FakeToolModel(messages=script(AIMessage(content="6 個です[1]。")))
        agent = build_agent(model, checkpointer=InMemorySaver(), extra_tools=[build_tool(t)])
        await run(agent, ctx(FakeSearch("在庫 6")), "SK-300 の在庫は？")
    assert t.agent_name not in model.tool_names[0] and model.tool_counts == [9]


async def test_forbidden_is_not_filled_in() -> None:
    with running() as (url, state):
        state["deny"] = True
        t = spec(url)
        model = FakeToolModel(
            messages=script(tool_call(t.agent_name, part="P-2011"), AIMessage(content="権限がありません。"))
        )
        agent = build_agent(model, checkpointer=InMemorySaver(), extra_tools=[build_tool(t)])
        c = ctx(FakeSearch("x"), mcp=mcp_run(t))
        state_, custom = await run(agent, c, "仕入単価は？")
    assert "見る権限が無い" in state_["messages"][-2].text
    # 表が返らなくても、何をどう呼んだかは段階に残す（specs/036 R1）
    step = steps_of(custom, t.agent_name)[-1]["output"]
    assert step["tool"] == "get_stock" and step["args"] == {"part": "P-2011"} and "rtt_ms" in step
    assert systems(custom)["mcp_denied"]["output"]["message"] == "見る権限がありません"
    assert not any(x.kind == "system" for x in c.registry.items())


async def test_hidden_columns_are_recorded() -> None:
    with running() as (url, state):
        state["hide"] = True
        t = spec(url)
        model = FakeToolModel(messages=script(tool_call(t.agent_name, part="P-2011"), AIMessage(content="x")))
        agent = build_agent(model, checkpointer=InMemorySaver(), extra_tools=[build_tool(t)])
        c = ctx(FakeSearch("x"), mcp=mcp_run(t))
        _, custom = await run(agent, c, "仕入単価は？")
    assert systems(custom)["mcp_denied"]["output"]["restricted"] == ["仕入単価（円）"]


async def test_down_server_is_reported_not_guessed() -> None:
    with running() as (url, state):
        state["down"] = True
        t = spec(url)
        model = FakeToolModel(messages=script(tool_call(t.agent_name, part="P-1042"), AIMessage(content="x")))
        agent = build_agent(model, checkpointer=InMemorySaver(), extra_tools=[build_tool(t)])
        c = ctx(FakeSearch("x"), mcp=mcp_run(t))
        state_, custom = await run(agent, c, "在庫は？")
    assert "確かめられませんでした" in state_["messages"][-2].text
    assert "mcp_unavailable" in systems(custom)


async def test_timeout_and_call_limit() -> None:
    with running() as (url, state):
        state["slow"] = 2
        t = spec(url, timeout=0.5)
        model = FakeToolModel(
            messages=script(
                tool_call(t.agent_name, part="A"),
                tool_call(t.agent_name, part="B"),
                AIMessage(content="x"),
            )
        )
        agent = build_agent(model, checkpointer=InMemorySaver(), extra_tools=[build_tool(t)])
        c = ctx(FakeSearch("x"), mcp=mcp_run(t, max_calls=1))
        _, custom = await run(agent, c, "在庫は？")
    kinds = systems(custom)
    assert "mcp_timeout" in kinds and kinds["mcp_limit"]["input"]["max_calls"] == 1


async def test_rows_are_truncated() -> None:
    with running() as (url, state):
        state["rows"] = 5
        t = spec(url)
        model = FakeToolModel(messages=script(tool_call(t.agent_name, part="A"), AIMessage(content="x")))
        agent = build_agent(model, checkpointer=InMemorySaver(), extra_tools=[build_tool(t)])
        c = ctx(FakeSearch("x"), mcp=mcp_run(t, max_rows=2))
        state_, custom = await run(agent, c, "在庫は？")
    assert "（全 5 行、うち 2 行を表示）" in state_["messages"][-2].text
    assert systems(custom)["mcp_truncated"]["output"] == {"total": 5, "kept": 2}


def test_use_systems_setting_is_clamped() -> None:
    assert AgentCfg.clamped({"use_systems": False}).use_systems is False
    assert AgentCfg.clamped({"use_systems": "no"}).use_systems is True


async def test_current_question_is_sent_back_until_system_is_checked() -> None:
    """今の値を問う質問: 注意を添え、文書だけで答えた下書きは 1 度差し戻す（R15）。"""
    with running() as (url, _):
        t = spec(url)
        model = FakeToolModel(
            messages=script(
                AIMessage(content="台帳では 6 個で、発注点 10 を下回っています[1]。"),
                tool_call(t.agent_name, part="SK-300"),
                AIMessage(content="今は 15 個で発注点 10 を満たしています[2]。台帳（9/30）は 6 個[1]。"),
            )
        )
        agent = build_agent(model, checkpointer=InMemorySaver(), extra_tools=[build_tool(t)])
        c = ctx(FakeSearch("部品台帳（9月30日現在）: SK-300 の在庫 6"), mcp=mcp_run(t))
        state, custom = await run(agent, c, "SK-300 は今、発注点を満たしていますか？")
    # 検索結果の外に注意を添え、記録に残す
    note = systems(custom)["current_note"]
    assert note["input"]["systems"] == ["ERP（資材・購買）"]
    assert any("社内システムで確かめてから" in m.text for m in model.calls[0])
    # 文書だけの下書きを差し戻し、記録に「今の値の確認」
    review = steps_of(custom, "review")[0]
    assert review["input"]["kind"] == "current" and review["label"] == "今の値の確認"
    # 要約には内部のツール名（erp__get_stock）ではなく、システムの名前とツールを書く
    assert steps_of(custom, "review")[-1]["summary"].endswith("ERP（資材・購買）の get_stock を実行")
    chose = [x["summary"] for x in systems_all(custom, "model_call")]
    assert "ツールを選んだ: ERP（資材・購買）の get_stock" in chose
    assert any("この下書きは文書（ある時点の記録）だけ" in m.text for m in model.calls[1])
    assert c.stats.reviewed("current") == 1 and c.mcp is not None and c.mcp.calls == 1
    assert "今は 15 個" in state["messages"][-1].text


async def test_current_review_names_systems_that_do_not_answer() -> None:
    """今の値を持つシステムが応答しないとき、注意と差し戻しに名前を書き、関係の無いシステムを呼ばせない（R17）。"""
    with running() as (url, _):
        t = spec(url)
        model = FakeToolModel(
            messages=script(
                AIMessage(content="台帳では 6 個です[1]。"),
                AIMessage(content="台帳（9/30）は 6 個[1]。今の在庫は確かめられませんでした。"),
            )
        )
        agent = build_agent(model, checkpointer=InMemorySaver(), extra_tools=[build_tool(t)])
        m = mcp_run(t)
        m.removed = {"cmms": ("mcp_unavailable", "保全システム", "接続を確かめられない")}
        c = ctx(FakeSearch("部品台帳（9月30日現在）: SK-300 の在庫 6"), mcp=m)
        await run(agent, c, "SK-300 の今の在庫は？")
    note = "保全システムは今応答しません"
    assert any(note in x.text for x in model.calls[0])
    assert any(note in x.text and "関係の無いシステムは呼ばず" in x.text for x in model.calls[1])


async def test_past_question_is_not_sent_back() -> None:
    with running() as (url, _):
        t = spec(url)
        model = FakeToolModel(messages=script(AIMessage(content="9 月末は 6 個です[1]。")))
        agent = build_agent(model, checkpointer=InMemorySaver(), extra_tools=[build_tool(t)])
        c = ctx(FakeSearch("部品台帳（9月30日現在）: SK-300 の在庫 6"), mcp=mcp_run(t))
        _, custom = await run(agent, c, "9 月末の SK-300 の在庫は？")
    assert "current_note" not in systems(custom)
    assert not steps_of(custom, "review") and c.stats.reviewed("current") == 0


def test_asks_current() -> None:
    from arag.agent.system_questions import asks_current

    asked = ["今の在庫は？", "現在の状態", "WO-1107 は終わった？", "まだ未入荷？", "Is it still open?"]
    # 社内システムにしか無い記録（仕入単価・作業指示・最近の記録）も確かめさせる
    asked += ["MS-30 の発注の仕入単価は？", "未着手の作業指示は？", "PM-04 の最近の保全作業", "recent work"]
    # 「いつ終わりましたか」・英語の「has it been resolved」も進み具合の質問
    asked += ["再設定はいつ終わりましたか？", "Has the noise on PM-04 been resolved?"]
    # 時点を言わない在庫・発注点・単価・リードタイム・入出庫・納期遅れは、社内システムの今の値を問う
    asked += ["軸受 6309ZZ の発注点はいくつですか？", "近接センサ PX-120 はどこにいくつありますか？",
              "Aster Seals に発注すると、届くまで何日かかりますか？",
              "軸受 6204ZZ-C3 の標準単価はいくらですか？",
              "納期を過ぎた発注はありますか？", "納期を過ぎても入荷し終えていない発注を全部挙げてください。",
              "Oリング P20 の 9 月以降の入出庫を教えてください。", "6206ZZ は今も発注できますか？",
              "11月16日の在庫の報告のあとで、新しく発注点を下回った部品はいくつありますか？"]  # fmt: skip
    for q in asked:
        assert asks_current(q), q
    not_asked = ["今回の会議の決定事項", "今後の予定", "今年度の計画", "9 月末の在庫"]
    # 文書の時点を名指しした質問は文書で答える（台帳・報告・議事録の値）
    not_asked += ["10月末の部品台帳で、状態が廃止になっている部品はいくつありますか？",
                  "11月16日の在庫の報告で発注点を下回っていた部品は？", "9月30日現在の在庫は？",
                  "SK-300 の 10 月の在庫の動きは？"]  # fmt: skip
    # 「〜ています」の「います」は「いま」ではない（hm01 で誤って注意を添えていた）
    not_asked += ["記録を何年間保存することになっていますか？", "どのくらいの頻度で行いますか？"]
    for q in not_asked:
        assert not asks_current(q), q


def test_prompt_names_systems_that_do_not_answer() -> None:
    """応答しない社内システムをプロンプトに書き、確かめられなかったと答えさせる（R17）。"""
    from arag.agent.middleware import system_prompt

    t = spec("http://x")
    m = mcp_run(t)
    m.removed = {"cmms": ("mcp_unavailable", "保全システム", "接続を確かめられない")}
    p = system_prompt(ctx(FakeSearch(), mcp=m))
    assert "使えるもの: ERP（資材・購買）" in p
    # システムごとに、管理者が書いた説明を添える（どのシステムに何があるかをモデルが選べるように）
    assert "- ERP（資材・購買）: 部品・在庫・発注" in p
    assert "応答しない社内システム: 保全システム" in p
    # 使えるシステムが 1 つも無くても、応答しないことは伝える
    m.usable = {}
    p = system_prompt(ctx(FakeSearch(), mcp=m))
    assert "応答しない社内システム: 保全システム" in p
    # 使える範囲の外・利用者の設定で外したものは書かない
    m.removed = {"cmms": ("mcp_filtered", "保全システム", "範囲の外")}
    assert "応答しない" not in system_prompt(ctx(FakeSearch(), mcp=m))


async def test_unfound_answer_is_sent_back_to_systems() -> None:
    """文書に無いと答えた下書きは、社内システムを確かめていなければ 1 度差し戻す（文書の検索が弱くても）。"""
    with running() as (url, _):
        t = spec(url)
        model = FakeToolModel(
            messages=script(
                AIMessage(content="資料からは 10 月の記録は見つかりませんでした。"),
                tool_call(t.agent_name, part="AL-01"),
                AIMessage(content="AL-01 の記録を確かめました[1]。"),
            )
        )
        agent = build_agent(model, checkpointer=InMemorySaver(), extra_tools=[build_tool(t)])
        c = ctx(FakeSearch(), mcp=mcp_run(t))
        _, custom = await run(agent, c, "SK-300 の 10 月の在庫の動きは？")
    review = steps_of(custom, "review")[0]
    assert review["input"]["kind"] == "system_gap" and review["label"] == "社内システムの確認"
    assert any("ERP（資材・購買）: 部品・在庫・発注" in m.text for m in model.calls[1])
    assert c.stats.reviewed("system_gap") == 1 and c.mcp is not None and c.mcp.calls == 1


async def test_unfound_answer_without_systems_is_not_sent_back_to_systems() -> None:
    with running() as (url, _):
        t = spec(url)
        model = FakeToolModel(messages=script(AIMessage(content="資料からは見つかりませんでした。")))
        agent = build_agent(model, checkpointer=InMemorySaver(), extra_tools=[build_tool(t)])
        c = ctx(FakeSearch(), mcp=mcp_run(t, usable=False))
        await run(agent, c, "組立ライン1号で 10 月に行った保全作業は？")
    assert c.stats.reviewed("system_gap") == 0


async def test_unfound_answer_unrelated_to_systems_is_not_sent_back() -> None:
    """質問の語がどのシステムの説明にも無ければ、文書に無いという答えを差し戻さない（hm57・hm59）。"""
    with running() as (url, _):
        t = spec(url)
        model = FakeToolModel(messages=script(AIMessage(content="資料からは見つかりませんでした。")))
        agent = build_agent(model, checkpointer=InMemorySaver(), extra_tools=[build_tool(t)])
        c = ctx(FakeSearch(), mcp=mcp_run(t))
        await run(agent, c, "ペナン工場の9月の生産台数は？")
    assert c.stats.reviewed("system_gap") == 0 and c.mcp is not None and c.mcp.calls == 0


def test_question_touches_systems() -> None:
    from arag.agent.system_questions import touches_systems

    t = spec("http://x")
    m = mcp_run(t)
    assert touches_systems("SK-300 の在庫は？", m)
    assert touches_systems("What is the current stock?", m) is False
    assert not touches_systems("クリーンルーム空調機 CR-02 の製造元はどこですか？", m)


# ── ERP の MCP サーバの返事（specs/033 R5・R12）──


async def test_too_many_is_recorded_and_not_guessed() -> None:
    with running() as (url, state):
        state["too_many"] = True
        t = spec(url)
        model = FakeToolModel(messages=script(tool_call(t.agent_name, part="軸受"), AIMessage(content="x")))
        agent = build_agent(model, checkpointer=InMemorySaver(), extra_tools=[build_tool(t)])
        c = ctx(FakeSearch("x"), mcp=mcp_run(t))
        state_, custom = await run(agent, c, "軸受の入出庫を全部")
    text = state_["messages"][-2].text
    assert "上限" in text and "期間で絞って" in text and "推測しない" in text
    out = systems(custom)["mcp_too_many"]["output"]
    assert out["total"] == 2400 and out["hint"] == "期間で絞ってください" and out["trace"] == {"id": "t1"}
    assert not any(x.kind == "system" for x in c.registry.items())


async def test_erp_unavailable_answer_from_server_is_reported() -> None:
    with running() as (url, state):
        state["erp_down"] = True
        t = spec(url)
        model = FakeToolModel(messages=script(tool_call(t.agent_name, part="P-1042"), AIMessage(content="x")))
        agent = build_agent(model, checkpointer=InMemorySaver(), extra_tools=[build_tool(t)])
        c = ctx(FakeSearch("x"), mcp=mcp_run(t))
        state_, custom = await run(agent, c, "在庫は？")
    assert "確かめられませんでした" in state_["messages"][-2].text
    assert "8 秒以内" in systems(custom)["mcp_unavailable"]["output"]["error"]


async def test_failed_call_marks_server_down_until_it_answers_again() -> None:
    """呼び出しで ERP が止まっていると分かったら、死活の記録（入力欄の札・次の質問）にすぐ反映する。

    3100 の試走: MCP サーバ（erp-mcp）は生きていて ping は通るが、その先の Odoo が止まっていると、
    札が「応答あり」のままだった。
    """
    seen: list[tuple[str, str | None]] = []

    async def on_health(name: str, reason: str | None, ms: int) -> None:
        seen.append((name, reason))

    with running() as (url, state):
        state["erp_down"] = True
        t = spec(url)
        script_ = script(tool_call(t.agent_name, part="P-1042"), AIMessage(content="x"))
        agent = build_agent(
            FakeToolModel(messages=script_), checkpointer=InMemorySaver(), extra_tools=[build_tool(t)]
        )
        m = mcp_run(t)
        m.on_health = on_health
        await run(agent, ctx(FakeSearch("x"), mcp=m), "在庫は？")
        assert seen and seen[-1][0] == "erp" and "8 秒以内" in (seen[-1][1] or "")
        state["erp_down"] = False
        script_ = script(tool_call(t.agent_name, part="P-1042"), AIMessage(content="x"))
        agent = build_agent(
            FakeToolModel(messages=script_), checkpointer=InMemorySaver(), extra_tools=[build_tool(t)]
        )
        m = mcp_run(t)
        m.on_health = on_health
        await run(agent, ctx(FakeSearch("x"), mcp=m), "在庫は？")
    assert seen[-1] == ("erp", None)


async def test_next_cursor_and_trace_are_kept_in_the_record() -> None:
    with running() as (url, state):
        state["more"] = True
        t = spec(url)
        model = FakeToolModel(messages=script(tool_call(t.agent_name, part="P-1042"), AIMessage(content="x")))
        agent = build_agent(model, checkpointer=InMemorySaver(), extra_tools=[build_tool(t)])
        c = ctx(FakeSearch("x"), mcp=mcp_run(t))
        await run(agent, c, "在庫は？")
    rec = next(x for x in c.registry.items() if x.kind == "system").record
    assert rec is not None and rec["next_cursor"] == "50" and rec["trace"]["id"] == "t2"


TABLE = "| 部品 | 在庫 | 発注点 |\n|---|---|---|\n| P-1042 | 6 | 10 |\n| P-1043 | 4 | 4 |"


async def _counted(answer: str) -> tuple[list[Any], FakeToolModel]:
    with running() as (url, _):
        t = spec(url)
        model = FakeToolModel(
            messages=script(
                tool_call(t.agent_name, part="P-1042"), AIMessage(content=answer), AIMessage(content="ok[2]")
            )
        )
        agent = build_agent(model, checkpointer=InMemorySaver(), extra_tools=[build_tool(t)])
        u = utility('{"kind": "docs", "queries": ["発注点を下回る部品"], "table": true}')
        c = ctx(FakeSearch(TABLE), mcp=mcp_run(t), utility_model=u)
        _, custom = await run(agent, c, "今、発注点を下回っている部品は何件ありますか？")
    return custom, model


async def test_counts_read_off_document_tables_are_checked_even_after_systems() -> None:
    """今の値を社内システムで確かめても、文書の表から数えた件数を書いたら table_query で数え直させる。

    3100 の試走: 在庫の報告のシートを検索で拾った行だけ数えて、11月16日を 14 件と答えた（本当は 50 件）。
    """
    custom, _ = await _counted("今は P-1042 が下回っています[2]。報告では 2 件でした[1]。")
    assert "table" in [s["input"]["kind"] for s in steps_of(custom, "review")]


async def test_system_only_answer_to_current_question_is_not_table_checked() -> None:
    custom, _ = await _counted("今は P-1042 が下回っています[2]。台帳でも P-1042 の在庫は 6 個です[1]。")
    assert not steps_of(custom, "review")


# ── 複数のシステムにまたがる質問（デモの試走: ERP は呼んだが、内線を名簿で確かめず手引きの古い値を答えた） ──


def directory_spec(url: str) -> ToolSpec:
    srv = ServerSpec(
        uuid.uuid4(), "directory", "社員名簿", url, "identity", None, None, "社員の部署・役職・内線"
    )
    return ToolSpec(srv, "find_people", "社員を探す（氏名・部署・役職・内線）", SCHEMA)


def test_missed_systems_names_the_uncalled_system_for_question_terms() -> None:
    from arag.agent.system_questions import missed_systems

    with running() as (url, _):
        erp, people = spec(url), directory_spec(url)
        m = mcp_run(erp)
        m.usable[people.agent_name] = people
        q = "MS-30 は今足りていますか？発注の問い合わせ先の担当者と内線も教えてください。"
        assert missed_systems(q, m, called={erp.agent_name}) == [("社員名簿", "find_people", "内線")]
        assert missed_systems(q, m, called={erp.agent_name, people.agent_name}) == []
        # どのシステムにも出てくる語・呼んだシステムの語だけなら差し戻さない
        assert missed_systems("SK-300 の在庫は？", m, called={erp.agent_name}) == []


def test_missed_systems_also_names_an_uncalled_tool_of_a_called_system() -> None:
    """デモの試走: 保全の作業指示だけ呼び、「最近の保全作業の記録」（作業の記録のツール）を呼ばなかった。"""
    from arag.agent.system_questions import missed_systems

    with running() as (url, _):
        stock = spec(url)
        # 説明の例に出てくる部品番号（「例 SK-300」）は語として数えない
        moves = ToolSpec(stock.server, "list_stock_moves", "部品の入出庫の履歴（例 SK-300）", SCHEMA)
        m = mcp_run(stock)
        m.usable[moves.agent_name] = moves
        q = "SK-300 の今の在庫と、最近の入出庫の履歴は？"
        want = [("ERP（資材・購買）", "list_stock_moves", "入出庫")]
        assert missed_systems(q, m, called={stock.agent_name}) == want
        assert missed_systems(q, m, called={stock.agent_name, moves.agent_name}) == []


async def test_answer_is_sent_back_to_a_system_the_question_needs_but_was_not_called() -> None:
    with running() as (url, _):
        erp, people = spec(url), directory_spec(url)
        model = FakeToolModel(
            messages=script(
                tool_call(erp.agent_name, part="P-1043"),
                AIMessage(content="今は 15 個です[1]。内線は 2201 です。"),
                AIMessage(content="今は 15 個です[1]。"),
            )
        )
        agent = build_agent(
            model, checkpointer=InMemorySaver(), extra_tools=[build_tool(erp), build_tool(people)]
        )
        m = mcp_run(erp)
        m.usable[people.agent_name] = people
        c = ctx(FakeSearch("x"), mcp=m)
        _, custom = await run(agent, c, "MS-30 は今足りていますか？問い合わせ先の内線も教えてください。")
    reviews = steps_of(custom, "review")
    assert {r["input"]["kind"] for r in reviews} == {"system_missed"}
    note = next(r["output"]["note"] for r in reviews if r.get("output"))
    assert "社員名簿" in note and "内線" in note


async def test_system_missed_review_names_every_uncalled_tool_at_once() -> None:
    """差し戻しは 1 回だけなので、呼んでいないツールを全部挙げる。

    デモの試走: 内線だけ挙げ、仕入先のリードタイムは文書の値のままだった。
    """
    with running() as (url, _):
        erp, people = spec(url), directory_spec(url)
        sup = ToolSpec(erp.server, "list_suppliers", "仕入先（名前・リードタイム・担当者）", SCHEMA)
        model = FakeToolModel(
            messages=script(
                tool_call(erp.agent_name, part="P-1043"),
                AIMessage(content="今は 15 個です[1]。リードタイムは 14 日、内線は 2201 です。"),
                AIMessage(content="今は 15 個です[1]。"),
            )
        )
        agent = build_agent(
            model,
            checkpointer=InMemorySaver(),
            extra_tools=[build_tool(erp), build_tool(people), build_tool(sup)],
        )
        m = mcp_run(erp)
        m.usable[people.agent_name] = people
        m.usable[sup.agent_name] = sup
        c = ctx(FakeSearch("x"), mcp=m)
        _, custom = await run(
            agent, c, "MS-30 は今足りていますか？仕入先のリードタイムと問い合わせ先の内線も教えてください。"
        )
    note = next(r["output"]["note"] for r in steps_of(custom, "review") if r.get("output"))
    assert "find_people" in note and "内線" in note
    assert "list_suppliers" in note


def test_called_tools_survive_history_summary() -> None:
    """履歴の要約でツールの結果が消えても、このターンに呼んだツールは呼んだと数える。

    デモの試走: 要約のあと list_below_reorder を呼んでいないと差し戻し、同じ呼び出しを繰り返させた。
    """
    from arag.agent.middleware import draft_of

    c = ctx(FakeSearch("x"))
    c.tool_seen.update({'erp__list_below_reorder:{"without_orders": true}', 'search:{"query": "x"}'})
    msg = ToolMessage(content="x", tool_call_id="1", name="directory__find_people")
    assert draft_of(c, [msg], "").mcp_called == {"erp__list_below_reorder", "directory__find_people"}
