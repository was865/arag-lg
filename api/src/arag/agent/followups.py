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
TIMEOUT_SEC = 5.0  # 候補は完了の後に届くので、待っても回答は遅れない（specs/028 T25。以前は 3 秒）
# 検索に出た資料の抜粋（T6b・T23）: 1 件の本文の先頭・件数・全体の字数の上限。答えの値が入るよう広めに渡す
EXCERPT_CHARS = 400
EXCERPT_MAX = 8
EXCERPT_TOTAL = 3200
# 直近のターン（T15）: 前の何ターンを渡すか・各回答の先頭の字数
HISTORY_TURNS = 3
HISTORY_ANSWER_CHARS = 600

_JSON = re.compile(r"\{.*\}", re.DOTALL)
_MARK = re.compile(r"\[\d+\]")


def width(text: str) -> float:
    """全角を 1、半角（ASCII）を 0.5 と数えた長さ。40 字の上限を英語の候補にも同じ見た目で当てる。"""
    return sum(0.5 if ord(c) < 0x80 else 1 for c in text)


@dataclass(frozen=True, slots=True)
class Candidate:
    """候補と、抜粋からそのまま写した答えの語句（T23）。"""

    q: str
    evidence: str


@dataclass(frozen=True, slots=True)
class Followups:
    questions: tuple[str, ...] = ()
    error: str = ""
    ms: int = 0
    raw: str = ""
    # 残した候補の根拠の語句（T23）
    evidence: tuple[dict[str, str], ...] = ()
    # 落とした候補と理由（no_evidence / already_answered / same_question）
    dropped: tuple[dict[str, str], ...] = ()


def parse(text: str, question: str) -> tuple[list[Candidate], str]:
    """モデルの出力から候補と根拠を取り出す。

    重複・元の質問と同じ文・40 字超（半角は半分）を落とし、最大 3 個。

    古い形（文字列の配列）は根拠が無く確かめられないので、失敗として扱う。
    """
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
    if any(isinstance(x, str) for x in raw):
        return [], "古い形（文字列の配列）で、根拠の語句が無い"
    out: list[Candidate] = []
    seen = {question.strip()}
    for x in raw:
        if not isinstance(x, dict):
            continue
        q, ev = x.get("q"), x.get("evidence")
        if not isinstance(q, str) or not isinstance(ev, str):
            continue
        q, ev = q.strip(), ev.strip()
        if not q or not ev or width(q) > MAX_CHARS or q in seen:
            continue
        seen.add(q)
        out.append(Candidate(q, ev))
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


_PUNCT = re.compile(r"[\s\W_]+")
_SPACE = re.compile(r"\s+")
_DIGIT_COMMA = re.compile(r"(?<=\d),(?=\d{3})")
# 数字・英数字の型番（2 字以上。18400・P-1042・SK-300・KG-5）
_CODE = re.compile(r"[0-9A-Za-z][0-9A-Za-z.\-]*[0-9A-Za-z]")


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def _same_key(text: str) -> str:
    """同じ文かを見るための形（NFKC・空白と句読点を除く）。"""
    return _PUNCT.sub("", _norm(text))


def _match_key(text: str) -> str:
    """語句がそのまま在るかを見る形（NFKC・空白を除く・数字の 3 桁区切りのカンマを除く）。"""
    return _SPACE.sub("", _DIGIT_COMMA.sub("", _norm(text)))


def _codes(text: str) -> set[str]:
    return {w for w in _CODE.findall(_DIGIT_COMMA.sub("", _norm(text))) if any(ch.isdigit() for ch in w)}


def check_candidates(
    cands: Sequence[Candidate],
    *,
    docs: Sequence[str],
    question: str,
    answer: str,
    history: Sequence[tuple[str, str]],
) -> tuple[list[Candidate], list[dict[str, str]]]:
    """候補を根拠の語句で確かめる（T23）。

    ① これまでの質問（今の質問を含む）と同じ文 → same_question。
    ② 根拠の語句が、渡した抜粋のどれにも部分文字列として無い → no_evidence。
    ③ 根拠の語句が、今と直近のターンの回答の文に既にある。または語句の中の数字・英数字の型番（2 字以上）が
       すべて回答の文にある → already_answered。
    """
    asked = {_same_key(q) for q, _ in history} | {_same_key(question)}
    sources = [_match_key(d) for d in docs]
    answers_text = "\n".join([_MARK.sub("", answer), *(_MARK.sub("", a) for _, a in history)])
    answers = _match_key(answers_text)
    answer_codes = _codes(answers_text)
    kept: list[Candidate] = []
    dropped: list[dict[str, str]] = []

    def drop(c: Candidate, reason: str) -> None:
        dropped.append({"question": c.q, "reason": reason, "evidence": c.evidence})

    for c in cands:
        ev = _match_key(c.evidence)
        if _same_key(c.q) in asked:
            drop(c, "same_question")
        elif not ev or not any(ev in s for s in sources):
            drop(c, "no_evidence")
        elif ev in answers or ((codes := _codes(c.evidence)) and codes <= answer_codes):
            drop(c, "already_answered")
        else:
            kept.append(c)
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
    """質問・回答・引用した資料の題名・検索に出た資料の抜粋から候補を作る（抜粋はデータとして囲む）。

    候補には抜粋から写した根拠の語句を付けさせ、コードで確かめて、資料に無いこと・既に答えたことを落とす。
    """
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
    cands, error = parse(text, question)
    kept, dropped = check_candidates(
        cands, docs=docs, question=question, answer=answer, history=history[-HISTORY_TURNS:]
    )
    return Followups(
        questions=tuple(c.q for c in kept),
        error=error,
        ms=ms(),
        raw=text[:1000],
        evidence=tuple({"question": c.q, "evidence": c.evidence} for c in kept),
        dropped=tuple(dropped),
    )
