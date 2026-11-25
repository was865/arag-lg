"""エージェントのツール（specs/005-agent B2・B3、R14〜R17）。"""

import re
import uuid
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.agent import ops
from arag.agent.config import AgentCfg
from arag.agent.context import RunContext
from arag.agent.ops import code_terms, find_named_documents, read_document
from arag.auth.principal import Principal
from arag.db.models import Section
from arag.ingest.index import QdrantIndex
from arag.search.schemas import SearchRequest
from arag.search.service import search

from .test_search import ALICE_P, FakeReranker, World, _deps
from .test_search import world as world  # fixture をこのモジュールでも使う

pytestmark = pytest.mark.integration


# ツールの中身は ToolOutput を返す（specs/037 R5）。ここでは主にモデルに渡す文を確かめる
async def op_search(*a: Any, **k: Any) -> str:
    return (await ops.op_search(*a, **k)).text


async def op_keyword_search(*a: Any, **k: Any) -> str:
    return (await ops.op_keyword_search(*a, **k)).text


async def op_list_documents(*a: Any, **k: Any) -> str:
    return (await ops.op_list_documents(*a, **k)).text


async def op_get_outline(*a: Any, **k: Any) -> str:
    return (await ops.op_get_outline(*a, **k)).text


async def op_read_section(*a: Any, **k: Any) -> str:
    return (await ops.op_read_section(*a, **k)).text


async def op_read_document(*a: Any, **k: Any) -> str:
    return (await ops.op_read_document(*a, **k)).text


async def op_table_query(*a: Any, **k: Any) -> str:
    return (await ops.op_table_query(*a, **k)).text


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

    async def fn(principal: Principal, req: SearchRequest):  # type: ignore[no-untyped-def]
        async with sm() as s:
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
    assert st[0]["parent_id"] == "c1" and st[0]["name"] == "embed"
    # 出典番号で文書に絞る
    n1 = ctx.registry.get(1)
    assert n1 is not None
    out3 = await op_search(ctx, ev, "c3", "MX-17", document_ids=["[1]"])
    docs = set(re.findall(r'文書="([^"]+)"', out3))
    assert docs == {n1.document_name}
    # 前のターンの番号など解決できない指定は無視して、絞らずに検索する
    out4 = await op_search(ctx, ev, "c4", "MX-17", document_ids=["[99]"])
    assert out4.startswith("注意: 文書の指定 [99]") and "絞らずに検索" in out4 and '<資料 n="1"' in out4
    # 構造: 資料の数（文の中の資料の囲みと同じ）。関連度は低くない
    got = await ops.op_search(ctx, ev, "c5", "MX-17")
    assert got.materials == got.text.count("<資料 n=") >= 1 and not got.weak


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
    low = await ops.op_search(ctx, Events(), "c9", "MX-17 対応")
    assert low.weak and low.materials > 0
    # 同じ ID は上書きされる。検索ごとに、内部の段が終わった順に出て、結果の行が最後に来る
    first_seen = {s["id"]: s["name"] for s in ev.steps()}
    names = list(first_seen.values())
    assert names == [
        "embed",
        "candidates",
        "rerank",
        "retrieve",
        "rewrite_query",
        "embed",
        "candidates",
        "rerank",
        "retrieve",
    ]
    rr = [s for s in ev.steps() if s["name"] == "rerank"][-1]
    assert rr["parent_id"] == "c1" and rr["output"]["selected"] and "上位" in rr["summary"]
    rw = next(s for s in ev.steps() if s["name"] == "rewrite_query" and s["status"] == "done")
    assert rw["output"] == {"rewritten": "MX-17 判定"}
    # 閾値以上なら書き換えない
    ctx2 = make_ctx(sessionmaker, qdrant_index, reranker=FakeReranker(constant=0.9), utility=util)
    ev2 = Events()
    out2 = await op_search(ctx2, ev2, "c1", "MX-17")
    assert {s["name"] for s in ev2.steps()} == {"retrieve", "embed", "candidates", "rerank"}
    assert not out2.startswith("注意: ")


async def test_keyword_search_requires_all_terms(
    world: World, sessionmaker: async_sessionmaker[AsyncSession], qdrant_index: QdrantIndex
) -> None:
    ctx = make_ctx(sessionmaker, qdrant_index)
    out = await op_keyword_search(ctx, Events(), "c1", ["MX-17", "部品"])
    assert "翌営業日" in out and "180 日" not in out
    assert "1 つ以上" in await op_keyword_search(ctx, Events(), "c1", ["  "])
    # 説明的な語が混ざって全語一致しなければ、型番だけで探し直す
    ev = Events()
    out2 = await op_keyword_search(ctx, ev, "c2", ["MX-17", "存在しない語"])
    assert out2.startswith("注意: すべての語を含む資料が無かったため、型番・番号だけで") and "<資料 " in out2
    assert "「存在しない語」の内容を search で" in out2
    got2 = await ops.op_keyword_search(ctx, Events(), "c2b", ["MX-17", "存在しない語"])
    assert got2.fallback == "codes" and got2.materials > 0
    done = [s for s in ev.steps() if s["status"] == "done" and s["name"] == "retrieve"]
    assert [s["label"] for s in done] == ["検索", "型番のみで再検索"]
    assert {s["parent_id"] for s in done} == {"c2"} and len({s["id"] for s in done}) == 2
    # 何が起きたかを各ステップの要約で説明する
    assert done[0]["summary"] == "0 件（「MX-17」「存在しない語」をすべて含む箇所なし）"
    assert done[0]["output"]["fallback"] == "codes"
    # 型番が無ければ（または型番でも無ければ）意味検索で補う
    ev3 = Events()
    out3 = await op_keyword_search(ctx, ev3, "c3", ["存在しない語", "別の語"])
    assert out3.startswith("注意: 語をすべて含む") and "<資料 " in out3
    got3 = await ops.op_keyword_search(ctx, Events(), "c3b", ["存在しない語", "別の語"])
    assert got3.fallback == "semantic"
    done3 = [s for s in ev3.steps() if s["status"] == "done" and s["name"] == "retrieve"]
    assert [s["input"]["mode"] for s in done3] == ["keyword", "hybrid"]
    assert done3[0]["output"]["fallback"] == "semantic" and done3[1]["label"] == "セマンティック検索で補完"


def test_code_terms() -> None:
    assert code_terms(["MX-17", "異常時の対応", "第12条", "ISO", "部品"]) == ["MX-17", "第12条", "ISO"]


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
    # 文書名（の一部）でも章立てを引ける
    assert "判定" in await op_get_outline(ctx, "a.m")


async def test_table_query_reads_the_section_table(
    world: World, sessionmaker: async_sessionmaker[AsyncSession], qdrant_index: QdrantIndex
) -> None:
    """章の本文にある表を条件で集計し、同じ章の出典番号で返す（specs/026 R12・R13）。"""
    ctx = make_ctx(sessionmaker, qdrant_index)
    outline = await op_get_outline(ctx, world.doc_a)
    sec_id = re.search(r"判定.*ID: ([0-9a-f-]{36})", outline)
    assert sec_id is not None
    async with sessionmaker() as s, s.begin():
        sec = await s.get(Section, uuid.UUID(sec_id.group(1)))
        assert sec is not None
        sec.text = "台帳\n\n| 部品 | 在庫 | 発注点 |\n|---|---|---|\n| P-1 | 6 | 10 |\n| P-2 | 4 | 4 |\n"
    out = await op_table_query(ctx, sec_id.group(1), "在庫 < 発注点", "発注点 - 在庫", call_id="c1")
    # 記録用の構造はツールの呼び出しごとに残し、モデルに渡す文には入れない（specs/028 T8）
    assert ctx.table_outputs["c1"]["rows_matched"] == 1 and "rows_matched" not in out
    assert out.startswith('<資料 n="1" 文書="a.md"') and "2 行）" in out and "1 行。" in out
    assert "| P-1 | 6 | 10 | 4 |" in out and "P-2" not in out
    # 読む（read_section）のと同じ出典番号になる
    assert '<資料 n="1"' in await op_read_section(ctx, sec_id.group(1))
    # 誤りは使える列を添えて返す。見えない利用者・表の無い章も案内する
    assert "使える列: 部品, 在庫, 発注点" in await op_table_query(ctx, "1", "数量 < 発注点")
    assert "table は 1〜1" in await op_table_query(ctx, "1", table=3)
    bob = make_ctx(sessionmaker, qdrant_index, p=Principal(user_id="bob"))
    assert "見つかりません" in await op_table_query(bob, sec_id.group(1), "在庫 < 発注点")
    other = re.search(r"補足.*ID: ([0-9a-f-]{36})", outline)
    assert other is not None and "表はありません" in await op_table_query(ctx, other.group(1))


async def test_table_query_errors_guide_and_repeated_failures_are_blocked(
    world: World, sessionmaker: async_sessionmaker[AsyncSession], qdrant_index: QdrantIndex
) -> None:
    """誤りには列名と例を添え、同じ指定での 2 度目の失敗は計算せずに止める（specs/026 T11・T12）。"""
    ctx = make_ctx(sessionmaker, qdrant_index)
    outline = await op_get_outline(ctx, world.doc_a)
    sec_id = re.search(r"判定.*ID: ([0-9a-f-]{36})", outline)
    assert sec_id is not None
    async with sessionmaker() as s, s.begin():
        sec = await s.get(Section, uuid.UUID(sec_id.group(1)))
        assert sec is not None
        sec.text = "台帳\n\n| 部品 | 単価 | 在庫 |\n|---|---|---|\n| P-1 | 500 | 6 |\n| P-2 | 900 | 4 |\n"
    sid = sec_id.group(1)
    # 集計関数は値と、その値を持つ行を返す
    out = await op_table_query(ctx, sid, "", "max(単価)")
    assert "max(単価) = 900" in out and "| P-2 | 900 | 4 |" in out
    # どの誤りにも列名と書き方の例が付く
    events = Events()
    first = await op_table_query(ctx, sid, "在庫 <", "", emit=events)
    assert "使える列: 部品, 単価, 在庫" in first and "書き方の例" in first
    assert not [s for s in events.steps() if s["name"] == "system"]
    # 同じ指定でもう一度失敗しそうな呼び出しは、計算せずに止め、記録に残す
    again = await op_table_query(ctx, sid, "在庫 <", "", emit=events)
    assert "同じ指定では失敗する" in again and "calculate" in again
    blocked = [s for s in events.steps() if s["name"] == "system"]
    assert len(blocked) == 1 and blocked[0]["input"]["kind"] == "repeat_blocked"
    assert blocked[0]["input"]["where"] == "在庫 <" and blocked[0]["input"]["source"] == sid
    # 指定を変えれば、また計算する
    assert "1 行。" in await op_table_query(ctx, sid, "在庫 < 5", "", emit=events)


async def test_candidates_step_lists_pre_rerank_hits(
    world: World, sessionmaker: async_sessionmaker[AsyncSession], qdrant_index: QdrantIndex
) -> None:
    ctx = make_ctx(sessionmaker, qdrant_index, reranker=FakeReranker(constant=0.9))
    ev = Events()
    await op_search(ctx, ev, "c1", "MX-17")
    cand = [s for s in ev.steps() if s["name"] == "candidates"][-1]
    hits = cand["output"]["hits"]
    assert hits and max(h["score"] for h in hits) == 1.0 and {"title", "heading"} <= set(hits[0])


async def test_read_document_reads_by_name_without_search(
    world: World, sessionmaker: async_sessionmaker[AsyncSession], qdrant_index: QdrantIndex
) -> None:
    ctx = make_ctx(sessionmaker, qdrant_index)
    # 文書名の一部・文書 ID のどちらでも、検索を通さず先頭から章ごとに読め、出典番号が付く
    by_name = await op_read_document(ctx, "a.m")
    assert '<資料 n="1"' in by_name and "即時停止" in by_name
    assert len(ctx.registry) >= 2  # 判定・補足の章
    by_id = await op_read_document(make_ctx(sessionmaker, qdrant_index), world.doc_a)
    assert "即時停止" in by_id
    # 上限を超えるときは、読んだ節数と続きの案内を返す
    got = await read_document(make_ctx(sessionmaker, qdrant_index), world.doc_a, budget=1)
    assert not isinstance(got, str) and got.truncated and got.sections == 1 and "get_outline" in got.text
    # 見えない文書・当てはまる文書が無い・複数ある
    bob = make_ctx(sessionmaker, qdrant_index, p=Principal(user_id="bob"))
    assert "ありません" in await op_read_document(bob, "a.md") or "見つかりません" in await op_read_document(
        bob, world.doc_a
    )
    assert "名前に含む文書は見つかりません" in await op_read_document(ctx, "存在しない文書")
    assert "複数あります" in await op_read_document(ctx, ".md")


async def test_find_named_documents_resolves_names_written_in_the_question(
    world: World, sessionmaker: async_sessionmaker[AsyncSession], qdrant_index: QdrantIndex
) -> None:
    ctx = make_ctx(sessionmaker, qdrant_index)
    got = await find_named_documents(ctx, "a.md を要約して")
    assert [name for _, name in got] == ["a.md"] and got[0][0] == world.doc_a
    assert await find_named_documents(ctx, "海外リージョンの対応は？") == []
    assert await find_named_documents(ctx, "zzz-none.pdf を読んで") == []
    # 見えない文書は決めない
    bob = make_ctx(sessionmaker, qdrant_index, p=Principal(user_id="bob"))
    assert await find_named_documents(bob, "a.md を要約して") == []
