"""続けて聞く質問の候補（specs/028 R1〜R5）。回答を確定した後に補助モデルで 2〜3 個作る。

ツール呼び出しは使わず JSON を文章として受け取る（understand と同じ流儀）。失敗・打ち切り・形式の誤りは
候補なしにして理由を返す（回答は遅らせない・失敗させない）。
"""

import asyncio
import json
import re
import time
import unicodedata
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
# 直近のターン（T15）: 前の何ターンを渡すか・各回答の先頭の字数
HISTORY_TURNS = 3
HISTORY_ANSWER_CHARS = 600

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
    # 会話で既に出たとして落とした候補と理由（T15）
    dropped: tuple[dict[str, str], ...] = ()


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


# 内容の語: 漢字・カタカナ・英数字と - の連なり（2 字以上）
_WORD = re.compile(r"[\u4e00-\u9fff々〆ヶ\u30a1-\u30faー0-9A-Za-z-]{2,}")
_SUFFIX = ("数", "名", "先", "額")
_PUNCT = re.compile(r"[\s\W_]+")


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def _same_key(text: str) -> str:
    """同じ文かを見るための形（NFKC・空白と句読点を除く）。"""
    return _PUNCT.sub("", _norm(text))


def drop_known(
    questions: list[str], question: str, answer: str, history: Sequence[tuple[str, str]]
) -> tuple[list[str], list[dict[str, str]]]:
    """会話で既に出たことを尋ねる候補を落とす（R2b）。

    ① これまでの質問（今の質問を含む）と同じ文。
    ② 内容の語がすべて、今のターンと前のターンの質問と回答に含まれる
    （3 字以上で末尾が「数・名・先・額」の語は、その 1 字を除いた形でも照合）。語が無い候補は落とさない。
    """
    asked = {_same_key(q) for q, _ in history} | {_same_key(question)}
    seen = _norm("\n".join([question, answer, *(f"{q}\n{a}" for q, a in history)]))
    kept: list[str] = []
    dropped: list[dict[str, str]] = []
    for q in questions:
        if _same_key(q) in asked:
            dropped.append({"question": q, "reason": "これまでの質問と同じ"})
            continue
        words = _WORD.findall(_norm(q))

        def known(w: str) -> bool:
            return w in seen or (len(w) >= 3 and w.endswith(_SUFFIX) and w[:-1] in seen)

        if words and all(known(w) for w in words):
            dropped.append({"question": q, "reason": f"語がすべて会話に出ている（{'・'.join(words)}）"})
            continue
        kept.append(q)
    return kept, dropped


_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uff00-\uffef]")


def language(question: str) -> str:
    """候補を書く言語。かな・漢字が無ければ英語（抜粋が日本語でも質問の言語に合わせる）。"""
    return "日本語" if _CJK.search(question) else "English（英語）"


def _message(
    question: str,
    answer: str,
    titles: list[str],
    docs: Sequence[str],
    history: Sequence[tuple[str, str]] = (),
) -> str:
    body = _MARK.sub("", answer).strip()[:ANSWER_CHARS]
    past = "\n\n".join(
        f"質問: {q.strip()}\n回答: {_MARK.sub('', a).strip()[:HISTORY_ANSWER_CHARS]}"
        for q, a in history[-HISTORY_TURNS:]
    )
    names = "\n".join(f"- {t}" for t in titles) or "（なし）"
    found = "\n\n".join(docs) or "（なし）"
    return (
        f"これまでの会話（古い順）:\n{past or '（なし）'}\n\n"
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
    history: Sequence[tuple[str, str]] = (),
    limit_sec: float = TIMEOUT_SEC,
) -> Followups:
    """質問・回答・引用した資料の題名・検索に出た資料の抜粋から候補を作る（抜粋はデータとして囲む）。"""
    t0 = time.monotonic()

    def ms() -> int:
        return round((time.monotonic() - t0) * 1000)

    msgs = [
        SystemMessage(load_prompt("agent_followups")),
        HumanMessage(_message(question, answer, titles, docs, history)),
    ]
    try:
        out = await asyncio.wait_for(model.ainvoke(msgs), timeout=limit_sec)
    except TimeoutError:
        return Followups(error=f"{limit_sec:g} 秒で打ち切った", ms=ms())
    except Exception as e:
        return Followups(error=f"{type(e).__name__}: {e}"[:200], ms=ms())
    text = str(out.text) if hasattr(out, "text") else str(out)
    questions, error = parse(text, question)
    kept, dropped = drop_known(questions, question, answer, history[-HISTORY_TURNS:])
    return Followups(questions=tuple(kept), error=error, ms=ms(), raw=text[:1000], dropped=tuple(dropped))
