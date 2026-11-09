"""保存済みの回答の引用番号を振り直す（データの移行）

回答の確定時の規則（api/src/arag/agent/citations.py の finalize_citations）を、
変更前に保存された回答にも当てる。

- 番号は回答に最初に出た順に 1, 2, 3…（以前は検索した順で、[3][7] のように飛んでいた）
- 出典は実際に引用した箇所だけ。引用の無い回答は出典も空（以前は検索した全資料を並べていた）
- citations 表の番号も合わせる

移行は自己完結させる（アプリのコードは将来変わるので import しない）。何度流しても結果は同じ。

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-09 17:30:00
"""

import json
import re
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MARK = re.compile(r"\[(\d+)\](?!\()")
_REPEAT = re.compile(r"\[(\d+)\](?:\[\1\](?!\())+")


def renumber(
    answer: str, cmap: dict[str, Any], sources: list[dict[str, Any]]
) -> tuple[str, dict[str, Any], list[dict[str, Any]], dict[int, int]]:
    """(回答, citation_map, sources, 旧番号→新番号) を返す。"""
    order: list[int] = []
    for m in _MARK.finditer(answer):
        n = int(m.group(1))
        if str(n) in cmap and n not in order:
            order.append(n)
    mapping = {old: new for new, old in enumerate(order, start=1)}

    def sub(m: re.Match[str]) -> str:
        new = mapping.get(int(m.group(1)))
        return f"[{new}]" if new else ""

    text = _REPEAT.sub(lambda m: f"[{m.group(1)}]", _MARK.sub(sub, answer))
    new_cmap = {str(new): cmap[str(old)] for old, new in mapping.items()}

    docs = {s["id"]: s for s in sources}
    sections = {(s["id"], sec["id"]): sec for s in sources for sec in s.get("sections", [])}
    out: dict[str, dict[str, Any]] = {}
    for new in sorted(int(k) for k in new_cmap):
        ref = new_cmap[str(new)]
        doc, sec = docs.get(ref["source_id"]), sections.get((ref["source_id"], ref["section_id"]))
        if doc is None or sec is None:
            continue
        meta = {k: v for k, v in doc.items() if k != "sections"}
        entry = out.setdefault(doc["id"], {**meta, "sections": []})
        entry["sections"].append({**sec, "n": new})
    return text, new_cmap, list(out.values()), mapping


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, answer_text, citation_map, sources FROM app.messages "
            "WHERE citation_map <> '{}'::jsonb OR jsonb_array_length(sources) > 0"
        )
    ).all()
    for mid, answer, cmap, sources in rows:
        text, new_cmap, new_sources, mapping = renumber(answer or "", cmap or {}, sources or [])
        if text == answer and new_cmap == cmap and new_sources == sources:
            continue
        bind.execute(
            sa.text(
                "UPDATE app.messages SET answer_text = :a, citation_map = CAST(:c AS jsonb), "
                "sources = CAST(:s AS jsonb) WHERE id = :id"
            ),
            {
                "a": text,
                "c": json.dumps(new_cmap, ensure_ascii=False),
                "s": json.dumps(new_sources, ensure_ascii=False),
                "id": mid,
            },
        )
        # citations 表: 引用されていない番号は消し、残りは一度負にしてから振り直す（一意制約を避ける）
        keep = list(mapping)
        if keep:
            bind.execute(
                sa.text("DELETE FROM app.citations WHERE message_id = :id AND NOT (ordinal = ANY(:keep))"),
                {"id": mid, "keep": keep},
            )
        else:
            bind.execute(sa.text("DELETE FROM app.citations WHERE message_id = :id"), {"id": mid})
        for old, new in mapping.items():
            bind.execute(
                sa.text("UPDATE app.citations SET ordinal = :neg WHERE message_id = :id AND ordinal = :old"),
                {"neg": -new, "id": mid, "old": old},
            )
        bind.execute(
            sa.text("UPDATE app.citations SET ordinal = -ordinal WHERE message_id = :id AND ordinal < 0"),
            {"id": mid},
        )


def downgrade() -> None:
    """データの移行なので戻さない（元の番号は残していない）。"""
