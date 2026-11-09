"""エージェントのツール（specs/005-agent B2・B3、R14〜R17）。"""

import re
import uuid
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.agent.config import AgentCfg
from arag.agent.context import RunContext
from arag.agent.ops import (
    op_get_outline,
    op_keyword_search,
    op_list_documents,
    op_read_section,
    op_search,
)
from arag.auth.principal import Principal
from arag.ingest.index import QdrantIndex
from arag.search.schemas import SearchRequest
from arag.search.service import search

from .test_search import ALICE_P, FakeReranker, World, _deps
from .test_search import world as world  # fixture をこのモジュールでも使う

pytestmark = pytest.mark.integration


def make_ctx(
    sm: async_sessionmaker[AsyncSession],
    qdrant_index: QdrantIndex,
    *,
    reranker: Any = None,
    utility: Any = None,
    p: Principal = ALICE_P,
    **kw: Any,
) -> RunContext:
    deps = _deps(qdrant_index, reranker=reranker or FakeReranker())

    async def fn(s: AsyncSession, principal: Principal, req: SearchRequest):  # type: ignore[no-untyped-def]
        return await search(s, deps, principal, req)

    return RunContext(principal=p, sessionmaker=sm, search=fn, utility_model=utility, **kw)


class Events(list[dict[str, Any]]):
    def __call__(self, e: dict[str, Any]) -> None:
        self.append(e)

    def steps(self) -> list[dict[str, Any]]:
        return [e["step"] for e in self if e["type"] == "step"]


async def test_search_registers_numbers_within_scope(
    world: World, sessionmaker: async_sessionmaker[AsyncSession], qdrant_index: QdrantIndex
) -> None:
    ctx = make_ctx(sessionmaker, qdrant_index)
    ev = Events()
    out = await op_search(ctx, ev, "c1", "MX-17")
    assert (
        '<資料 n="1"' in out and "秘密メモ" not in out and "古い記録" not in out
    )  # Bob の文書・ごみ箱は出ない
    first = len(ctx.registry)
    assert first >= 2
    out2 = await op_search(ctx, ev, "c2", "MX-17")  # 同じチャンクは同じ番号
    assert len(ctx.registry) == first and '<資料 n="1"' in out2
    st = ev.steps()
    assert st[0]["parent_id"] == "c1" and st[0]["status"] == "running" and st[1]["status"] == "done"
    # 出典番号で文書に絞る
    n1 = ctx.registry.get(1)
    assert n1 is not None
    out3 = await op_search(ctx, ev, "c3", "MX-17", document_ids=["[1]"])
    docs = set(re.findall(r'文書="([^"]+)"', out3))
    assert docs == {n1.document_name}
    # 前のターンの番号など解決できない指定は無視して、絞らずに検索する
    out4 = await op_search(ctx, ev, "c4", "MX-17", document_ids=["[99]"])
    assert out4.startswith("注意: 文書の指定 [99]") and "絞らずに検索" in out4 and '<資料 n="1"' in out4


async def test_crag_rewrites_when_scores_are_low(
    world: World, sessionmaker: async_sessionmaker[AsyncSession], qdrant_index: QdrantIndex
) -> None:
    util = GenericFakeChatModel(messages=iter([AIMessage(content="「MX-17 判定」")]))
    ctx = make_ctx(
        sessionmaker,
        qdrant_index,
        reranker=FakeReranker(constant=0.1),
        utility=util,
        cfg=AgentCfg(grade_threshold=0.3, max_retrieve_retries=1),
        question="MX-17 はどうする？",
    )
    ev = Events()
    out = await op_search(ctx, ev, "c1", "MX-17 対応")
    # 書き換えても低いままなら、関連が薄いことを結果に添える
    assert out.startswith("注意: ") and "見つからなかった" in out
    names = [s["name"] for s in ev.steps() if s["status"] != "running"]
    assert names == ["retrieve", "rewrite_query", "retrieve"]
    rw = next(s for s in ev.steps() if s["name"] == "rewrite_query" and s["status"] == "done")
    assert rw["output"] == {"rewritten": "MX-17 判定"}
    # 閾値以上なら書き換えない
    ctx2 = make_ctx(sessionmaker, qdrant_index, reranker=FakeReranker(constant=0.9), utility=util)
    ev2 = Events()
    out2 = await op_search(ctx2, ev2, "c1", "MX-17")
    assert {s["name"] for s in ev2.steps()} == {"retrieve"}
    assert not out2.startswith("注意: ")


async def test_keyword_search_requires_all_terms(
    world: World, sessionmaker: async_sessionmaker[AsyncSession], qdrant_index: QdrantIndex
) -> None:
    ctx = make_ctx(sessionmaker, qdrant_index)
    out = await op_keyword_search(ctx, Events(), "c1", ["MX-17", "部品"])
    assert "翌営業日" in out and "180 日" not in out
    assert "1 つ以上" in await op_keyword_search(ctx, Events(), "c1", ["  "])
    # 全語を含む資料が無ければ意味検索で補う
    ev = Events()
    out2 = await op_keyword_search(ctx, ev, "c2", ["MX-17", "存在しない語"])
    assert out2.startswith("注意: 語をすべて含む") and "<資料 " in out2
    assert [s["input"]["mode"] for s in ev.steps() if s["status"] == "done"] == ["keyword", "hybrid"]
    # 補った検索も同じツール呼び出しの子として出す（画面で見えるように）
    done = [s for s in ev.steps() if s["status"] == "done"]
    assert {s["parent_id"] for s in done} == {"c2"} and len({s["id"] for s in done}) == 2
    # 何が起きたかを各ステップの要約で説明する
    assert done[0]["summary"] == "0 件（「MX-17」「存在しない語」をすべて含む箇所なし）"
    assert done[1]["label"] == "意味検索で補う"


async def test_list_outline_and_read_section(
    world: World, sessionmaker: async_sessionmaker[AsyncSession], qdrant_index: QdrantIndex
) -> None:
    ctx = make_ctx(sessionmaker, qdrant_index)
    listing = await op_list_documents(ctx)
    assert "a.md" in listing and "org.md" in listing
    assert "bob.md" not in listing and "trash.md" not in listing and "arch.md" not in listing
    assert "a.md" in await op_list_documents(ctx, "a.m") and "org.md" not in await op_list_documents(
        ctx, "a.m"
    )
    # 名前に無い語（内容の語）で探したら本文の検索へ誘導する
    assert "search を使って" in await op_list_documents(ctx, "海外リージョン")
    # 添付で文書を絞った run は、その文書しか見えない
    only = make_ctx(sessionmaker, qdrant_index, document_ids=[uuid.UUID(world.doc_org)])
    assert "a.md" not in await op_list_documents(only)

    outline = await op_get_outline(ctx, world.doc_a)
    assert "判定" in outline and "補足" in outline
    sec_id = re.search(r"判定.*ID: ([0-9a-f-]{36})", outline)
    assert sec_id is not None
    body = await op_read_section(ctx, sec_id.group(1))
    assert '<資料 n="1"' in body and "即時停止" in body
    assert len(ctx.registry) == 1

    # 出典番号から文書・セクションへ
    await op_search(ctx, Events(), "c1", "部品 翌営業日")
    n = next(k for k in ctx.registry.numbers() if "翌営業日" in ctx.registry.get(k).text)  # type: ignore[union-attr]
    assert "章立て" in await op_get_outline(ctx, f"[{n}]")
    assert "到着" in await op_read_section(ctx, str(n))

    # 見えない文書・不正な参照
    bob = make_ctx(sessionmaker, qdrant_index, p=Principal(user_id="bob"))
    assert "見つかりません" in await op_get_outline(bob, world.doc_a)
    assert "見つかりません" in await op_read_section(bob, sec_id.group(1))
    assert "見つかりません" in await op_get_outline(ctx, "なにか")
