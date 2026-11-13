"""続けて聞く質問の候補（specs/028 R1〜R5）。回答を確定した後に補助モデルで 2〜3 個作る。

ツール呼び出しは使わず JSON を文章として受け取る（understand と同じ流儀）。失敗・打ち切り・形式の誤りは
候補なしにして理由を返す（回答は遅らせない・失敗させない）。
"""

import asyncio
import json
import re
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from arag.agent.citations import Cited
from arag.agent.thinking import split_thinking
from arag.prompts import load_prompt

MAX_QUESTIONS = 3
MAX_CHARS = 40
ANSWER_CHARS = 1500
TIMEOUT_SEC = 3.0
# 検索に出た資料の抜粋（T6b）: 1 件の本文の先頭・件数・全体の字数の上限
EXCERPT_CHARS = 240
EXCERPT_MAX = 8
EXCERPT_TOTAL = 2400

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


def excerpts(items: Iterable[Cited]) -> list[str]:
    """検索に出た資料（引用しなかったものも含む）を「題名（見出し）+ 本文の先頭」にする。

    スコアの高い順（スコアの無い、節をまるごと読んだものは後ろ）に最大 EXCERPT_MAX 件、
    全体で EXCERPT_TOTAL 字まで。
    """
    ranked = sorted(items, key=lambda c: (c.score is None, -(c.score or 0.0), c.n))
    out: list[str] = []
    total = 0
    for c in ranked[:EXCERPT_MAX]:
        head = f"{c.document_name}（{c.heading_path}）" if c.heading_path else c.document_name
        block = f"{head}\n{' '.join(c.text.split())[:EXCERPT_CHARS]}"
        if total + len(block) > EXCERPT_TOTAL:
            block = block[: EXCERPT_TOTAL - total]
        if not block.strip():
            break
        out.append(block)
        total += len(block)
    return out


_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uff00-\uffef]")


def language(question: str) -> str:
    """候補を書く言語。かな・漢字が無ければ英語（抜粋が日本語でも質問の言語に合わせる）。"""
    return "日本語" if _CJK.search(question) else "English（英語）"


def _message(question: str, answer: str, titles: list[str], docs: Sequence[str]) -> str:
    body = _MARK.sub("", answer).strip()[:ANSWER_CHARS]
    names = "\n".join(f"- {t}" for t in titles) or "（なし）"
    found = "\n\n".join(docs) or "（なし）"
    return (
        f"質問:\n{question.strip()}\n\n回答:\n{body}\n\n引用した資料の題名:\n{names}\n\n"
        f"検索に出た資料の抜粋:\n<資料>\n{found}\n</資料>\n\n"
        f"候補を書く言語: {language(question)}"
    )


async def suggest(
    model: BaseChatModel,
    question: str,
    answer: str,
    titles: list[str],
    docs: Sequence[str] = (),
    *,
    limit_sec: float = TIMEOUT_SEC,
) -> Followups:
    """質問・回答・引用した資料の題名・検索に出た資料の抜粋から候補を作る（抜粋はデータとして囲む）。"""
    t0 = time.monotonic()

    def ms() -> int:
        return round((time.monotonic() - t0) * 1000)

    msgs = [
        SystemMessage(load_prompt("agent_followups")),
        HumanMessage(_message(question, answer, titles, docs)),
    ]
    try:
        out = await asyncio.wait_for(model.ainvoke(msgs), timeout=limit_sec)
    except TimeoutError:
        return Followups(error=f"{limit_sec:g} 秒で打ち切った", ms=ms())
    except Exception as e:
        return Followups(error=f"{type(e).__name__}: {e}"[:200], ms=ms())
    text = str(out.text) if hasattr(out, "text") else str(out)
    questions, error = parse(text, question)
    return Followups(questions=tuple(questions), error=error, ms=ms(), raw=text[:1000])
