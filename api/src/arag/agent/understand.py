"""質問の理解（specs/026 R1〜R4）。補助モデルで種類・検索クエリ・表の集計の要否を得る。

ツール呼び出しは使わず JSON を文章として受け取るので、どのモデルでも動く。読めなければ質問文をそのまま使う。
"""

import asyncio
import json
import re
from dataclasses import dataclass, replace
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage

from arag.agent.thinking import split_thinking
from arag.prompts import load_prompt

MAX_QUERIES = 3
QUERY_MAX_CHARS = 300
HISTORY_TURNS = 2
HISTORY_ANSWER_CHARS = 300
TIMEOUT_SEC = 15.0

Kind = Literal["docs", "chat"]


@dataclass(frozen=True, slots=True)
class Understanding:
    kind: Kind = "docs"
    queries: tuple[str, ...] = ()
    table: bool = False
    # モデルは true と言ったが、出力の形の指定（「表にして」）だけなので false にした（specs/026 T28）
    table_overridden: bool = False
    # 記録用: モデルの出力そのままと、読めなかったときの理由
    raw: str = ""
    error: str = ""


def fallback(question: str, error: str = "", raw: str = "") -> Understanding:
    return Understanding(queries=(question.strip()[:QUERY_MAX_CHARS],), raw=raw, error=error)


_JSON = re.compile(r"\{.*\}", re.DOTALL)


def parse(text: str, question: str) -> Understanding:
    """モデルの出力から JSON を取り出す。形が崩れていても、使える部分は使う。"""
    _, body = split_thinking(text)
    m = _JSON.search(body)
    if not m:
        return fallback(question, "JSON が見つからない", text)
    try:
        data: Any = json.loads(m.group(0))
    except ValueError:
        return fallback(question, "JSON を読めない", text)
    if not isinstance(data, dict):
        return fallback(question, "JSON がオブジェクトでない", text)
    kind: Kind = "chat" if data.get("kind") == "chat" else "docs"
    queries: list[str] = []
    raw_queries = data.get("queries")
    for q in raw_queries if isinstance(raw_queries, list) else []:
        if isinstance(q, str) and (q := q.strip()[:QUERY_MAX_CHARS]) and q not in queries:
            queries.append(q)
    if kind == "docs" and not queries:
        queries = [question.strip()[:QUERY_MAX_CHARS]]
    return Understanding(
        kind=kind,
        queries=tuple(queries[:MAX_QUERIES]) if kind == "docs" else (),
        table=data.get("table") is True,
        raw=text,
    )


# 「表にして」「一覧で」などは答えの形の指定であって、表の集計ではない（specs/026 T28）
_FORM = re.compile(
    r"表に(して|まとめ)|表で|表形式|一覧に(して|まとめ)|一覧で|まとめて|in a table|as a table|tabulate",
    re.IGNORECASE,
)
_AGGREGATE = re.compile(
    r"合計|総|平均|最大|最小|最も|一番|何件|何個|いくつ|いくら|下回|上回|以上|以下|未満|超|"
    r"total|sum|average|how many|below|above|least|most",
    re.IGNORECASE,
)


def guard_table(u: Understanding, question: str) -> Understanding:
    """出力の形の言い方があり、集計の語が無い質問は、モデルが true と言っても table=false にする。"""
    if u.table and _FORM.search(question) and not _AGGREGATE.search(question):
        return replace(u, table=False, table_overridden=True)
    return u


def history_text(messages: list[AnyMessage]) -> str:
    """直近の会話（質問と回答の先頭）。ツールの結果は入れない。"""
    turns: list[tuple[str, str]] = []
    for m in messages:
        if isinstance(m, HumanMessage):
            turns.append((m.text, ""))
        elif isinstance(m, AIMessage) and not m.tool_calls and turns:
            _, answer = split_thinking(m.text)
            turns[-1] = (turns[-1][0], answer.strip())
    lines = []
    for q, a in turns[-HISTORY_TURNS:]:
        lines.append(f"利用者: {q.strip()[:QUERY_MAX_CHARS]}")
        if a:
            lines.append(f"アシスタント: {a[:HISTORY_ANSWER_CHARS]}")
    return "\n".join(lines)


async def understand(model: BaseChatModel | None, history: list[AnyMessage], question: str) -> Understanding:
    if model is None:
        return fallback(question, "補助モデルが無い")
    past = history_text(history)
    body = (f"直近の会話:\n{past}\n\n" if past else "") + f"今回の質問:\n{question.strip()}"
    try:
        out = await asyncio.wait_for(
            model.ainvoke([SystemMessage(load_prompt("agent_understand")), HumanMessage(body)]),
            timeout=TIMEOUT_SEC,
        )
    except Exception as e:
        return fallback(question, f"{type(e).__name__}: {e}"[:200])
    return guard_table(parse(out.text, question), question)
