"""回答の流れのイベントとステップの列を、分岐ごとに固定する（specs/029 T2。作り直しの物差し）。

runner の `_stream` で偽モデルを流し、画面に届くイベント（本文の差分・取り消し・ステップ・出典）、
モデルが受け取った最後のメッセージ、会話の状態に残ったメッセージを記録して、保存した列と比べる。
期待を作り直すときは `ARAG_UPDATE_SNAPSHOTS=1 uv run pytest tests/test_agent_flow_snapshots.py`。
作り直しの前後で列が変わったら、それは挙動の変化なので、理由を確かめてから更新する。
"""

import json
import os
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from arag.agent.config import AgentCfg
from arag.agent.context import RunContext
from arag.agent.events import RUN_EVENT
from arag.agent.graph import build_agent
from arag.agent.runner import _stream, _Turn
from arag.auth.principal import Principal

from .agent_fakes import FakeSearch, FakeToolModel, null_sessionmaker, script, tool_call

SNAPSHOTS = Path(__file__).parent / "fixtures" / "agent_flow_snapshots.json"
UPDATE = os.environ.get("ARAG_UPDATE_SNAPSHOTS") == "1"

TABLE = "| 部品 | 在庫 | 発注点 |\n|---|---|---|\n| P-1042 | 6 | 10 |\n| P-1043 | 4 | 4 |"
TABLE_DRAFT = "| 項目 | HP-300 | HP-320 |\n|---|---|---|\n| 在庫 | 6 [1] | 4 [1] |"
GAP_DRAFT = "変更点はトルク値です[1]。在庫数は資料に記載されていません。"


class ListSink:
    """EventSink の代わり（検証して溜めるだけ）。"""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit(self, ev: dict[str, Any]) -> None:
        self.events.append(RUN_EVENT.validate_python(ev).model_dump(mode="json", exclude_none=True))


def utility(*outputs: str) -> FakeToolModel:
    return FakeToolModel(messages=script(*(AIMessage(content=o) for o in outputs)))


_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_CALL = re.compile(r"call_[0-9a-f]{8}")


def _normalize(data: Any) -> Any:
    """所要時間を除き、実行ごとに変わる ID（UUID・ツール呼び出し）を出た順の番号にする。

    ステップの節点の名前（`node`、029 R3 で足す）はここでは比べず、別のテストで確かめる。
    """

    def drop_ms(x: Any) -> Any:
        if isinstance(x, dict):
            return {k: drop_ms(v) for k, v in x.items() if k not in {"duration_ms", "ms", "node"}}
        if isinstance(x, list):
            return [drop_ms(v) for v in x]
        return x

    text = json.dumps(drop_ms(data), ensure_ascii=False, sort_keys=True)
    for pattern, name in ((_UUID, "uuid"), (_CALL, "call")):
        seen: dict[str, str] = {}
        text = pattern.sub(lambda m, s=seen, n=name: s.setdefault(m.group(0), f"<{n}-{len(s) + 1}>"), text)
    return json.loads(text)


def _message(m: BaseMessage) -> dict[str, Any]:
    out: dict[str, Any] = {"type": m.type, "text": m.text}
    if isinstance(m, AIMessage) and m.tool_calls:
        out["tools"] = [tc["name"] for tc in m.tool_calls]
    if isinstance(m, ToolMessage):
        out = {"type": m.type, "name": m.name, "status": m.status}
    return out


async def _turn(agent: Any, c: RunContext, q: str, thread: str) -> tuple[list[dict[str, Any]], Any]:
    sink, turn = ListSink(), _Turn()
    config = {"configurable": {"thread_id": thread}, "recursion_limit": c.cfg.max_steps * 3 + 10}
    await _stream(agent, config, c, sink, turn, q)  # type: ignore[arg-type]
    return sink.events, await agent.aget_state({"configurable": {"thread_id": thread}})


def _ctx(search: FakeSearch, **kw: Any) -> RunContext:
    return RunContext(
        principal=Principal(user_id="u"), sessionmaker=null_sessionmaker, search=search, question="q", **kw
    )


async def flow(
    model: FakeToolModel, search: FakeSearch, question: str, *, before: list[str] | None = None, **kw: Any
) -> dict[str, Any]:
    """1 ターンを流して記録する。before があれば、同じスレッドで先にそのターンを流す（記録はしない）。"""
    agent = build_agent(model, checkpointer=InMemorySaver())
    for q in before or []:
        await _turn(agent, _ctx(search, **kw), q, "s")
    c = _ctx(search, **kw)
    first = len(model.calls)
    events, state = await _turn(agent, c, question, "s")
    msgs = state.values.get("messages", [])
    start = max(i for i, m in enumerate(msgs) if isinstance(m, HumanMessage))
    return _normalize(
        {
            "events": events,
            "model_calls": [_message(call[-1]) for call in model.calls[first:]],
            "messages": [_message(m) for m in msgs[start:]],
            "stats": {
                k: v
                for k, v in vars(c.stats).items()
                if k in {"model_calls", "tool_calls", "gap_reviews", "table_reviews", "number_reviews"}
                or k.startswith("empty")
                or k == "rewrites_discarded"
            },
        }
    )


Case = Callable[[], Awaitable[dict[str, Any]]]


async def _answer() -> dict[str, Any]:
    model = FakeToolModel(messages=script(AIMessage(content="停止する【1】。根拠なし[9]")))
    return await flow(model, FakeSearch("MX-17 は即時停止を推奨する。"), "MX-17 はどうする？")


async def _tool_then_answer() -> dict[str, Any]:
    model = FakeToolModel(
        messages=script(tool_call("search", query="MX-17 手順"), AIMessage(content="停止する[1]"))
    )
    return await flow(model, FakeSearch("MX-17 は即時停止を推奨する。"), "MX-17 はどうする？")


async def _gap() -> dict[str, Any]:
    model = FakeToolModel(
        messages=script(
            AIMessage(content=GAP_DRAFT),
            tool_call("search", query="SK-300 部品台帳 在庫"),
            AIMessage(content="変更点はトルク値です[1]。在庫は SK-300 のとおりです[2]。"),
        )
    )
    return await flow(model, FakeSearch("HP-300 第3版", "SK-300 在庫"), "第3版の変更点と、関連部品の在庫は？")


async def _gap_twice() -> dict[str, Any]:
    model = FakeToolModel(
        messages=script(
            AIMessage(content="資料に記載されていません。"),
            AIMessage(content="やはり資料に記載されていません。"),
        )
    )
    return await flow(model, FakeSearch("本文"), "q")


async def _table() -> dict[str, Any]:
    model = FakeToolModel(
        messages=script(AIMessage(content="P-1042 と P-1043 です[1]"), AIMessage(content="P-1042 です[1]"))
    )
    u = utility('{"kind": "docs", "queries": ["在庫が発注点を下回る部品"], "table": true}')
    return await flow(model, FakeSearch(TABLE), "在庫が発注点を下回る部品は？", utility_model=u)


async def _numbers() -> dict[str, Any]:
    model = FakeToolModel(
        messages=script(
            AIMessage(content="単価は 17,800 円です[1]"), AIMessage(content="単価は 17,800 円です[1]")
        )
    )
    return await flow(model, FakeSearch("シールキット SK-300 の単価は 18,400 円。"), "SK-300 の単価は？")


async def _gap_then_numbers() -> dict[str, Any]:
    """調べ残しの差し戻しの書き直しに資料に無い数字 → 続けて数字の差し戻し（同じ呼び出しの中で 2 度）。"""
    model = FakeToolModel(
        messages=script(
            AIMessage(content="単価は資料に記載されていません[1]。"),
            AIMessage(content="単価は 17,800 円です[1]。"),
            AIMessage(content="単価は 18,400 円です[1]。"),
        )
    )
    return await flow(model, FakeSearch("シールキット SK-300 の単価は 18,400 円。"), "SK-300 の単価は？")


async def _empty_retry() -> dict[str, Any]:
    model = FakeToolModel(messages=script(AIMessage(content=""), AIMessage(content="答えは 5 年です[1]")))
    return await flow(model, FakeSearch("保存は 5 年"), "保存期間は？")


async def _empty_retry_then_tools() -> dict[str, Any]:
    model = FakeToolModel(
        messages=script(AIMessage(content=""), tool_call("search", query="保存期間"), AIMessage(content=""))
    )
    return await flow(model, FakeSearch("保存は 5 年"), "保存期間は？")


async def _empty_failed() -> dict[str, Any]:
    model = FakeToolModel(messages=script(AIMessage(content=""), AIMessage(content="")))
    return await flow(model, FakeSearch("保存は 5 年"), "保存期間は？")


async def _empty_after_send_back_uses_draft() -> dict[str, Any]:
    model = FakeToolModel(
        messages=script(AIMessage(content=GAP_DRAFT), AIMessage(content=""), AIMessage(content=""))
    )
    return await flow(model, FakeSearch("HP-300 第3版", "SK-300 在庫"), "第3版の変更点と、関連部品の在庫は？")


async def _empty_after_send_back_retried() -> dict[str, Any]:
    model = FakeToolModel(
        messages=script(
            AIMessage(content=GAP_DRAFT),
            AIMessage(content=""),
            AIMessage(content="変更点はトルク値です[1]。在庫は 6 個です[2]。"),
        )
    )
    return await flow(
        model, FakeSearch("HP-300 第3版", "SK-300 在庫 6"), "第3版の変更点と、関連部品の在庫は？"
    )


async def _rewrite_reply_uses_draft() -> dict[str, Any]:
    model = FakeToolModel(
        messages=script(
            AIMessage(content=TABLE_DRAFT),
            AIMessage(content="了解いたしました。指示に従い、table_query を使用して回答します[1]。"),
        )
    )
    u = utility('{"kind": "docs", "queries": ["在庫が発注点を下回る部品"], "table": true}')
    return await flow(model, FakeSearch(TABLE), "在庫が発注点を下回る部品は？", utility_model=u)


async def _rewrite_after_tool_kept() -> dict[str, Any]:
    model = FakeToolModel(
        messages=script(
            AIMessage(content=TABLE_DRAFT),
            tool_call("table_query", source="1", where="在庫 < 発注点"),
            AIMessage(content="了解しました。P-1042 です。"),
        )
    )
    u = utility('{"kind": "docs", "queries": ["在庫が発注点を下回る部品"], "table": true}')
    return await flow(model, FakeSearch(TABLE), "在庫が発注点を下回る部品は？", utility_model=u)


async def _chat() -> dict[str, Any]:
    model = FakeToolModel(
        messages=script(AIMessage(content="一回目[1]"), AIMessage(content="どういたしまして"))
    )
    u = utility('{"kind": "docs", "queries": ["q"]}', '{"kind": "chat", "queries": [], "table": false}')
    return await flow(model, FakeSearch("本文"), "ありがとう", before=["質問"], utility_model=u)


async def _step_budget() -> dict[str, Any]:
    model = FakeToolModel(
        messages=script(
            tool_call("search", query="a"), tool_call("search", query="b"), AIMessage(content="まとめ[1]")
        )
    )
    return await flow(model, FakeSearch("本文"), "q", cfg=AgentCfg(max_steps=3))


async def _second_turn() -> dict[str, Any]:
    """前のターンの状態（差し戻し済み・空のやり直し済み）を次のターンに持ち越さない。"""
    model = FakeToolModel(
        messages=script(
            AIMessage(content=""),
            AIMessage(content="資料に記載されていません。"),
            AIMessage(content="一回目の答え[1]。"),
            tool_call("search", query="b"),
            AIMessage(content=""),
            AIMessage(content="二回目も資料に記載されていません。"),
            AIMessage(content="二回目の答え[1]。"),
        )
    )
    return await flow(model, FakeSearch("本文"), "二つ目", before=["一つ目"])


CASES: dict[str, Case] = {
    "answer": _answer,
    "tool_then_answer": _tool_then_answer,
    "gap": _gap,
    "gap_twice": _gap_twice,
    "table": _table,
    "numbers": _numbers,
    "gap_then_numbers": _gap_then_numbers,
    "empty_retry": _empty_retry,
    "empty_retry_then_tools": _empty_retry_then_tools,
    "empty_failed": _empty_failed,
    "empty_after_send_back_uses_draft": _empty_after_send_back_uses_draft,
    "empty_after_send_back_retried": _empty_after_send_back_retried,
    "rewrite_reply_uses_draft": _rewrite_reply_uses_draft,
    "rewrite_after_tool_kept": _rewrite_after_tool_kept,
    "chat": _chat,
    "step_budget": _step_budget,
    "second_turn": _second_turn,
}


def _load() -> dict[str, Any]:
    return json.loads(SNAPSHOTS.read_text()) if SNAPSHOTS.exists() else {}


@pytest.mark.parametrize("name", list(CASES))
async def test_flow_matches_snapshot(name: str) -> None:
    got = await CASES[name]()
    if UPDATE:
        saved = _load()
        saved[name] = got
        SNAPSHOTS.write_text(json.dumps(dict(sorted(saved.items())), ensure_ascii=False, indent=1) + "\n")
        return
    expected = _load().get(name)
    assert expected is not None, f"{name} の記録がありません（ARAG_UPDATE_SNAPSHOTS=1 で作る）"
    assert got == expected
