"""理由の裏付けの確認（specs/031 R12）。

「なぜ」を尋ねる質問で、小さいモデルは別々の資料の事実をつないで理由を作りがち（「第3版でグリスを KG-5 に
変えた」＋「台帳で KG-2 は廃止予定」→「漏れ対策のため KG-2 は廃止予定」。どの資料にもそうは書いていない）。
回答が引用した資料に、その理由が質問の事柄の理由として書かれているかを、補助モデルに 1 回だけ判定させる。
"""

import asyncio
import json
import re
import time
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from arag.prompts import load_prompt

# 理由を尋ねる質問（日本語・英語）
WHY = re.compile(r"なぜ|何故|どうして|理由|原因|\bwhy\b|\breasons?\b", re.IGNORECASE)
TIMEOUT_SEC = 20.0
MATERIAL_CHARS = 1500
_JSON = re.compile(r"\{.*\}", re.DOTALL)


def asks_reason(question: str) -> bool:
    return bool(WHY.search(question))


@dataclass(frozen=True, slots=True)
class ReasonCheck:
    supported: bool | None  # 判定できなければ None（差し戻さない）
    why: str = ""
    raw: str = ""
    error: str = ""
    ms: int = 0


def parse(text: str) -> ReasonCheck:
    m = _JSON.search(text or "")
    if not m:
        return ReasonCheck(None, raw=text[:500], error="JSON が無い")
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return ReasonCheck(None, raw=text[:500], error="JSON を読めない")
    # 事柄そのものが資料にあるか・理由がその事柄に結び付けて書かれているか、の 2 つで判定する
    # （1 つの真偽だけを聞くと、小さいモデルは「資料と回答が一致している」で true にしがち）
    parts = [data.get("subject_in_material"), data.get("reason_linked")]
    if "supported" in data and not any(isinstance(p, bool) for p in parts):
        parts = [data.get("supported")]
    if not all(isinstance(p, bool) for p in parts):
        return ReasonCheck(None, raw=text[:500], error="判定の項目が無い")
    why = str(data.get("why") or "")[:300]
    if subject := str(data.get("subject") or "").strip():
        why = f"{subject}: {why}" if why else subject
    return ReasonCheck(all(parts), why=why, raw=text[:500])


async def check_reason(
    model: BaseChatModel, question: str, answer: str, materials: dict[int, str]
) -> ReasonCheck:
    """回答の理由が、引用した資料に質問の事柄の理由として書かれているか。失敗したら supported=None。"""
    docs = "\n\n".join(
        f'<資料 n="{n}">\n{text[:MATERIAL_CHARS]}\n</資料>' for n, text in sorted(materials.items())
    )
    body = f"質問:\n{question.strip()}\n\n回答:\n{answer.strip()}\n\n回答が引用した資料:\n{docs}"
    t0 = time.perf_counter()
    try:
        out = await asyncio.wait_for(
            model.ainvoke([SystemMessage(load_prompt("reason_check")), HumanMessage(body)]),
            timeout=TIMEOUT_SEC,
        )
    except Exception as e:
        ms = round((time.perf_counter() - t0) * 1000)
        return ReasonCheck(None, error=f"{type(e).__name__}: {e}"[:200], ms=ms)
    got = parse(out.text)
    return ReasonCheck(got.supported, got.why, got.raw, got.error, round((time.perf_counter() - t0) * 1000))
