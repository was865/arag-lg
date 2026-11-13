"""続けて聞く質問の候補（specs/028 R1〜R5）。回答を確定した後に補助モデルで 2〜3 個作る。

ツール呼び出しは使わず JSON を文章として受け取る（understand と同じ流儀）。失敗・打ち切り・形式の誤りは
候補なしにして理由を返す（回答は遅らせない・失敗させない）。
"""

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from arag.agent.thinking import split_thinking
from arag.prompts import load_prompt

MAX_QUESTIONS = 3
MAX_CHARS = 40
ANSWER_CHARS = 1500
TIMEOUT_SEC = 3.0

_JSON = re.compile(r"\{.*\}", re.DOTALL)
_MARK = re.compile(r"\[\d+\]")


def width(text: str) -> float:
    """全角を 1、半角（ASCII）を 0.5 と数えた長さ。40 字の上限を英語の候補にも同じ見た目で当てる。"""
    return sum(0.5 if ord(c) < 0x80 else 1 for c in text)


@dataclass(frozen=True, slots=True)
class Followups:
    questions: tuple[str, ...] = ()
    error: str = ""
    ms: int = 0
    raw: str = ""


def parse(text: str, question: str) -> tuple[list[str], str]:
    """モデルの出力から候補を取り出す（重複・元の質問と同じ文・40 字超（半角は半分）を落とし、最大 3 個）。"""
    _, body = split_thinking(text)
    m = _JSON.search(body)
    if not m:
        return [], "JSON が見つからない"
    try:
        data: Any = json.loads(m.group(0))
    except ValueError:
        return [], "JSON を読めない"
    raw = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return [], "questions が配列でない"
    out: list[str] = []
    seen = {question.strip()}
    for q in raw:
        if not isinstance(q, str) or not (q := q.strip()) or width(q) > MAX_CHARS or q in seen:
            continue
        seen.add(q)
        out.append(q)
        if len(out) == MAX_QUESTIONS:
            break
    return out, ""


def _message(question: str, answer: str, titles: list[str]) -> str:
    body = _MARK.sub("", answer).strip()[:ANSWER_CHARS]
    docs = "\n".join(f"- {t}" for t in titles) or "（なし）"
    return f"質問:\n{question.strip()}\n\n回答:\n{body}\n\n引用した資料の題名:\n{docs}"


async def suggest(
    model: BaseChatModel,
    question: str,
    answer: str,
    titles: list[str],
    *,
    limit_sec: float = TIMEOUT_SEC,
) -> Followups:
    """質問・回答・引用した資料の題名から候補を作る。資料の本文は渡さない（指示の混入を避ける）。"""
    t0 = time.monotonic()

    def ms() -> int:
        return round((time.monotonic() - t0) * 1000)

    msgs = [SystemMessage(load_prompt("agent_followups")), HumanMessage(_message(question, answer, titles))]
    try:
        out = await asyncio.wait_for(model.ainvoke(msgs), timeout=limit_sec)
    except TimeoutError:
        return Followups(error=f"{limit_sec:g} 秒で打ち切った", ms=ms())
    except Exception as e:
        return Followups(error=f"{type(e).__name__}: {e}"[:200], ms=ms())
    text = str(out.text) if hasattr(out, "text") else str(out)
    questions, error = parse(text, question)
    return Followups(questions=tuple(questions), error=error, ms=ms(), raw=text[:1000])
