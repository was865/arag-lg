"""前のターンで回答が引用した文書（追質問で「さっきの資料」と言われたときの手がかり）。

回答を確定したとき、引用した文書名を回答のメッセージ（additional_kwargs の cited_documents）に残してある。
それが無い古い記録は、回答の [n] を同じターンの検索結果の <資料 n="…" 文書="…"> と突き合わせて文書名にする。
検索に出ただけで引用されなかった文書は含めない。
"""

import re
from dataclasses import dataclass

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage

from arag.agent.domain.thinking import split_thinking

_DOC = re.compile(r'<資料 n="(\d+)" 文書="([^"]*)"')
_MARK = re.compile(r"\[(\d+)\](?!\()")
DOC_CHARS = 60


@dataclass(frozen=True, slots=True)
class Turn:
    question: str
    answer: str
    cited: tuple[str, ...]
    cited_ids: tuple[str, ...] = ()


def turns(messages: list[AnyMessage]) -> list[Turn]:
    """質問から始まる区切りごとに、質問・最後の回答・引用した文書名（出た順、重複なし）を返す。"""
    out: list[Turn] = []
    docs: dict[int, str] = {}
    question, answer = "", ""
    saved: list[str] = []  # 回答のメッセージに残した、引用した文書名（確定のときに記録）
    saved_ids: list[str] = []
    started = False

    def close() -> None:
        if not started:
            return
        nums = [int(n) for n in _MARK.findall(answer)]
        names: list[str] = list(saved)
        for n in nums:
            name = docs.get(n, "")
            if name and name not in names:
                names.append(name)
        out.append(Turn(question, answer, tuple(names), tuple(saved_ids)))

    for m in messages:
        if isinstance(m, HumanMessage):
            close()
            started, question, answer, docs, saved, saved_ids = True, m.text, "", {}, [], []
        elif isinstance(m, ToolMessage):
            for n, name in _DOC.findall(m.text):
                docs.setdefault(int(n), name.strip()[:DOC_CHARS])
        elif isinstance(m, AIMessage) and not m.tool_calls:
            answer = split_thinking(m.text)[1].strip()
            kept = m.additional_kwargs.get("cited_documents")
            saved = [str(x)[:DOC_CHARS] for x in kept] if isinstance(kept, list) else []
            ids = m.additional_kwargs.get("cited_document_ids")
            saved_ids = [str(x) for x in ids] if isinstance(ids, list) else []
    close()
    return out


def cited_documents(messages: list[AnyMessage], *, limit: int = 8) -> list[str]:
    """前のターンの回答が引用した文書。新しいターンのものを先に、重複なし。"""
    names: list[str] = []
    for t in reversed(turns(messages)):
        for name in t.cited:
            if name not in names:
                names.append(name)
    return names[:limit]


def last_cited_scope(messages: list[AnyMessage]) -> tuple[list[str], list[str]]:
    """直近で引用のあった回答の、文書 ID と文書名（「さっきの資料」に検索を絞る）。ID が無ければ空。"""
    for t in reversed(turns(messages)):
        if t.cited:
            return (list(t.cited_ids), list(t.cited)) if len(t.cited_ids) == len(t.cited) else ([], [])
    return [], []
