"""出典番号の管理と引用記号の正規化（specs/005-agent R15・R16・R18、design §3.1）。"""

import re
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Any

from arag.search.schemas import SearchHit

SNIPPET_MAX = 1200
MAX_RANGE = 10


@dataclass(frozen=True, slots=True)
class Cited:
    n: int
    item_id: uuid.UUID  # チャンク ID（read_section ではセクション ID）
    document_id: uuid.UUID
    document_name: str
    section_id: uuid.UUID
    heading_path: str
    page: int | None
    block_type: str
    text: str
    context: str = ""
    score: float | None = None


class CitationRegistry:
    """run 内の出典番号。同じチャンク・セクションは同じ番号（ターンごとに 1 から）。"""

    def __init__(self) -> None:
        self._by_key: dict[str, int] = {}
        self._items: dict[int, Cited] = {}

    def __len__(self) -> int:
        return len(self._items)

    def get(self, n: int) -> Cited | None:
        return self._items.get(n)

    def numbers(self) -> list[int]:
        return list(self._items)

    def _add(self, key: str, make: Any) -> int:
        if key in self._by_key:
            return self._by_key[key]
        n = len(self._items) + 1
        self._by_key[key] = n
        self._items[n] = make(n)
        return n

    def add_hit(self, h: SearchHit) -> int:
        return self._add(
            f"chunk:{h.chunk_id}",
            lambda n: Cited(
                n=n,
                item_id=h.chunk_id,
                document_id=h.document_id,
                document_name=h.document_name,
                section_id=h.section_id,
                heading_path=h.heading_path,
                page=h.page_start,
                block_type=h.block_type,
                text=h.text,
                context=h.context,
                score=h.score,
            ),
        )

    def add_section(
        self,
        *,
        document_id: uuid.UUID,
        document_name: str,
        section_id: uuid.UUID,
        heading_path: str,
        page: int | None,
        text: str,
    ) -> int:
        return self._add(
            f"section:{section_id}",
            lambda n: Cited(
                n=n,
                item_id=section_id,
                document_id=document_id,
                document_name=document_name,
                section_id=section_id,
                heading_path=heading_path,
                page=page,
                block_type="section",
                text=text,
            ),
        )

    def sources(self, only: set[int] | None = None) -> tuple[dict[int, dict[str, str]], list[dict[str, Any]]]:
        """引用番号 → 出典の対応と、文書ごとにまとめた出典（右パネル用）。"""
        cmap: dict[int, dict[str, str]] = {}
        docs: dict[uuid.UUID, dict[str, Any]] = {}
        for n, c in self._items.items():
            if only is not None and n not in only:
                continue
            cmap[n] = {"source_id": str(c.document_id), "section_id": str(c.item_id)}
            src = docs.setdefault(
                c.document_id,
                {"id": str(c.document_id), "title": c.document_name, "sections": [], "score": None},
            )
            src["sections"].append(
                {
                    "id": str(c.item_id),
                    "n": n,
                    "heading": c.heading_path,
                    "body": c.text[:SNIPPET_MAX],
                    "block_type": c.block_type,
                    "page": c.page,
                }
            )
            if c.score is not None and (src["score"] is None or c.score > src["score"]):
                src["score"] = c.score
        return cmap, list(docs.values())


def _attr(v: str) -> str:
    return v.replace('"', "”").replace("<", "＜").replace("\n", " ")


def _body(v: str) -> str:
    # 資料タグを本文から閉じたり開いたりできないようにする（R16）
    return v.replace("</資料", "＜/資料").replace("<資料", "＜資料")


def format_material(n: int, c: Cited) -> str:
    attrs = f'n="{n}" 文書="{_attr(c.document_name)}" 見出し="{_attr(c.heading_path)}"'
    if c.page is not None:
        attrs += f' ページ="{c.page}"'
    body = _body(c.text)
    if c.context:
        body = f"（文脈: {_body(c.context)}）\n{body}"
    return f"<資料 {attrs}>\n{body}\n</資料>"


_FULLWIDTH = re.compile(r"[【［]\s*([0-9０-９]+)\s*[】］]")
_GROUP = re.compile(r"\[\s*([0-9０-９]+(?:\s*[,，、\-–]\s*[0-9０-９]+)+)\s*\](?!\()")
_SINGLE_FW = re.compile(r"\[\s*([０-９]+)\s*\]")
_MARK = re.compile(r"\[(\d+)\](?!\()")
# 小さいモデルは資料タグ <資料 n="1"> をまねて [n=1] や [資料 n="1"] と書くことがある
_ATTR = re.compile(r"\[\s*(?:資料\s*)?n\s*=\s*[\"']?([0-9０-９]+)[\"']?\s*\]")


def _num(s: str) -> int:
    return int(unicodedata.normalize("NFKC", s))


def _expand(m: re.Match[str]) -> str:
    inner = unicodedata.normalize("NFKC", m.group(1))
    out: list[int] = []
    for part in re.split(r"\s*[,，、]\s*", inner):
        if re.fullmatch(r"\d+\s*[-–]\s*\d+", part):
            a, b = (int(x) for x in re.split(r"\s*[-–]\s*", part))
            if b < a or b - a >= MAX_RANGE:
                return m.group(0)
            out.extend(range(a, b + 1))
        elif part.isdigit():
            out.append(int(part))
        else:
            return m.group(0)
    return "".join(f"[{n}]" for n in out)


def normalize_markers(text: str) -> str:
    """【1】［1］[１] [n=1] → [1]、[1,2] [1、2] → [1][2]、[1-3] → [1][2][3]。Markdown のリンクは触らない。"""
    text = _ATTR.sub(lambda m: f"[{_num(m.group(1))}]", text)
    text = _FULLWIDTH.sub(lambda m: f"[{_num(m.group(1))}]", text)
    text = _SINGLE_FW.sub(lambda m: f"[{_num(m.group(1))}]", text)
    return _GROUP.sub(_expand, text)


def cited_numbers(text: str) -> list[int]:
    seen: list[int] = []
    for m in _MARK.finditer(text):
        n = int(m.group(1))
        if n not in seen:
            seen.append(n)
    return seen


def strip_unknown(text: str, valid: set[int]) -> str:
    return _MARK.sub(lambda m: m.group(0) if int(m.group(1)) in valid else "", text)
