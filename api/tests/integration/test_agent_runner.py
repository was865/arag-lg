"""run の実行・保存・取消・分岐（specs/005-agent C2、R2・R6・R12・R23・R25）。"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.agent.runner import ResolvedModels, Runner, RunnerDeps, claim, execute_run, reap_stale
from arag.agent.service import RunRequest, create_run
from arag.agent.stream import read_events, request_cancel
from arag.auth.principal import Principal
from arag.db.models import AuditLog, Citation, Message, Run, Thread
from arag.errors import ApiError
from arag.settings import Settings

from ..agent_fakes import (
    FailingModel,
    FakeSearch,
    FakeToolModel,
    StatusError,
    fake_hit,
    idle_utility,
    prompt_script,
    script,
    tool_call,
)

pytestmark = pytest.mark.integration
ALICE = Principal(user_id="alice")


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    r = Redis.from_url(Settings().redis_url, decode_responses=True)
    try:
        await r.ping()
    except Exception as e:
        pytest.skip(f"redis に接続できません: {e}")
    yield r
    await r.aclose()


def make_deps(
    sm: async_sessionmaker[AsyncSession], redis: Redis, model: Any, search: Any = None, **kw: Any
) -> RunnerDeps:
    def resolve(model_id: str | None) -> ResolvedModels:
        if model_id == "broken":
            raise RuntimeError("目録にありません")
        # 質問の整理（specs/026）は別の補助モデルに任せ、会話モデルの台本を減らさない
        return ResolvedModels(id=model_id or "fake", model=model, utility=idle_utility())

    return RunnerDeps(
        sessionmaker=sm,
        redis=redis,
        checkpointer=InMemorySaver(),
        search=search or FakeSearch("MX-17 は即時停止を推奨する。"),
        resolve_models=resolve,
        cancel_poll_sec=0.05,
        **kw,
    )


async def start(
    sm: async_sessionmaker[AsyncSession], query: str, thread: Thread | None = None, **kw: Any
) -> tuple[Thread, Run]:
    async with sm() as s:
        th, run = await create_run(
            s, ALICE, thread, RunRequest(query=query, **kw), kw.get("model_id") or "fake"
        )
        await s.commit()
    async with sm() as s:
        assert await claim(s, "test") == run.id
    return th, run


async def events(redis: Redis, run_id: uuid.UUID) -> list[dict[str, Any]]:
    out = []
    async for item in read_events(redis, str(run_id), block_ms=500):
        if item is None:
            break
        out.append(json.loads(item[2]))
    return out


async def test_run_completes_and_persists(
    sessionmaker: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    model = FakeToolModel(
        messages=script(tool_call("search", query="MX-17"), AIMessage(content="即時停止です[1]。"))
    )
    deps = make_deps(sessionmaker, redis, model)
    _th, run = await start(sessionmaker, "MX-17 はどうする？")
    assert await execute_run(deps, run.id) == "completed"
    evs = await events(redis, run.id)
    types = [e["type"] for e in evs]
    assert types[0] == "run.started" and types[-1] == "run.completed"
    assert "step" in types and "sources" in types and "answer.delta" in types
    done = evs[-1]
    assert done["answer"] == "即時停止です[1]。" and done["no_answer_reason"] is None
    assert set(done["citation_map"]) == {"1"} and done["tokens_out"] > 0
    async with sessionmaker() as s:
        msg = await s.get(Message, run.message_id)
        assert msg is not None and msg.ordinal == 1 and msg.status == "completed"
        assert msg.answer_text == "即時停止です[1]。" and msg.steps and msg.sources[0]["title"] == "規程.pdf"
        cites = list(await s.scalars(select(Citation).where(Citation.message_id == msg.id)))
        assert [c.ordinal for c in cites] == [1] and cites[0].document_title == "規程.pdf"
        r = await s.get(Run, run.id)
        assert r is not None and r.status == "completed" and r.finished_at is not None
        audit = (await s.scalars(select(AuditLog).where(AuditLog.action == "chat.run"))).one()
        assert audit.detail is not None and "MX-17" not in json.dumps(audit.detail, ensure_ascii=False)


async def test_second_turn_and_branch(sessionmaker: async_sessionmaker[AsyncSession], redis: Redis) -> None:
    model = FakeToolModel(
        messages=script(
            AIMessage(content="一回目"), AIMessage(content="二回目"), AIMessage(content="一回目のやり直し")
        )
    )
    deps = make_deps(sessionmaker, redis, model)
    th, r1 = await start(sessionmaker, "質問1")
    await execute_run(deps, r1.id)
    _, r2 = await start(sessionmaker, "質問2", th)
    await execute_run(deps, r2.id)
    async with sessionmaker() as s:
        assert [m.ordinal for m in await s.scalars(select(Message).where(Message.thread_id == th.id))] == [
            1,
            2,
        ]
    # 1 ターン目から分岐（質問の編集）
    _, r3 = await start(sessionmaker, "質問1（編集）", th, from_message_id=r1.message_id)
    await execute_run(deps, r3.id)
    async with sessionmaker() as s:
        msgs = list(await s.scalars(select(Message).where(Message.thread_id == th.id)))
        assert [(m.ordinal, m.answer_text) for m in msgs] == [(1, "一回目のやり直し")]
    # 分岐した実行のモデル入力に 2 ターン目は含まれない
    texts = [m.text for m in model.calls[-1]]
    assert "質問2" not in texts and "質問1" not in texts
    assert any(t.startswith("質問1（編集）") for t in texts)


async def test_cancel_saves_partial_and_next_run_works(
    sessionmaker: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    class Slow(FakeSearch):
        """2 回目（モデルのツール呼び出し）だけ遅い検索。1 回目はシステムの最初の検索。"""

        async def __call__(self, *a: Any) -> Any:
            if len(self.requests) == 1:
                await asyncio.sleep(5)
            return await super().__call__(*a)

    model = FakeToolModel(messages=script(tool_call("search", query="a"), AIMessage(content="次の回答")))
    deps = make_deps(sessionmaker, redis, model, search=Slow("本文"))
    runner = Runner(deps, database_url=Settings().database_url)
    th, run = await start(sessionmaker, "遅い質問")
    task = asyncio.create_task(runner._run_one(run.id))
    await asyncio.sleep(0.3)
    await request_cancel(redis, str(run.id))
    assert await asyncio.wait_for(task, 3) == "cancelled"
    assert (await events(redis, run.id))[-1]["type"] == "run.cancelled"
    async with sessionmaker() as s:
        msg = await s.get(Message, run.message_id)
        assert msg is not None and msg.status == "cancelled"
    # 応答の無いツール呼び出しが残っていても次のターンは動く
    _, r2 = await start(sessionmaker, "次", th)
    assert await execute_run(deps, r2.id) == "completed"


async def test_model_unavailable_fails_with_message(
    sessionmaker: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    deps = make_deps(sessionmaker, redis, FakeToolModel(messages=script()))
    _, run = await start(sessionmaker, "q", model_id="broken")
    assert await execute_run(deps, run.id) == "failed"
    last = (await events(redis, run.id))[-1]
    assert last["type"] == "run.failed" and last["code"] == "model_unavailable"
    async with sessionmaker() as s:
        msg = await s.get(Message, run.message_id)
        assert msg is not None and msg.no_answer_reason == "generation_failed" and msg.answer_text


async def test_no_sources_reason(sessionmaker: async_sessionmaker[AsyncSession], redis: Redis) -> None:
    # 0 件なので書き換え → 再検索 → 回答なし
    model = FakeToolModel(messages=script(tool_call("search", query="x"), AIMessage(content="")))
    deps = make_deps(sessionmaker, redis, model, search=FakeSearch())
    _, run = await start(sessionmaker, "q")
    await execute_run(deps, run.id)
    done = (await events(redis, run.id))[-1]
    assert done["no_answer_reason"] == "no_sources" and "見つかりませんでした" in done["answer"]


async def test_reap_stale_and_conflict(sessionmaker: async_sessionmaker[AsyncSession], redis: Redis) -> None:
    deps = make_deps(sessionmaker, redis, FakeToolModel(messages=script()))
    th, run = await start(sessionmaker, "q")
    with pytest.raises(ApiError) as ei:
        await start(sessionmaker, "q2", th)
    assert ei.value.status == 409
    async with sessionmaker() as s, s.begin():
        r = await s.get(Run, run.id)
        assert r is not None
        r.heartbeat_at = datetime.now(UTC) - timedelta(minutes=5)
    assert await reap_stale(deps, timedelta(seconds=60)) == 1
    last = (await events(redis, run.id))[-1]
    assert last["type"] == "run.failed" and last["code"] == "runner_lost"


async def test_utility_model_rewrites_low_score_search(
    sessionmaker: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    """runner が書き換え用モデルを RunContext に渡し、低スコアのとき再検索する（R17）。"""
    model = FakeToolModel(messages=script(AIMessage(content="答え[1]")))
    # 質問の整理（読めない出力 → 質問文のまま検索）と書き換えは並行に呼ばれうるので、プロンプトで答えを分ける
    utility = prompt_script(
        agent_understand=[AIMessage(content="？")],
        agent_rewrite=[AIMessage(content="社外持出し 規程")],
    )
    search = FakeSearch("無関係な本文")
    search.hits = [fake_hit("無関係な本文", score=0.05)]
    deps = make_deps(sessionmaker, redis, model, search)
    deps.resolve_models = lambda mid: ResolvedModels(id="fake", model=model, utility=utility)
    _th, run = await start(sessionmaker, "持ち出しの規定は？")
    assert await execute_run(deps, run.id) == "completed"
    assert [r.query for r in search.requests] == ["持ち出しの規定は？", "社外持出し 規程"]


async def test_uncited_answer_is_no_relevant_sources(
    sessionmaker: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    model = FakeToolModel(
        messages=script(
            tool_call("search", query="x"),
            AIMessage(content="資料からは見つかりませんでした。"),
            # 調べ残しの差し戻しのあとも見つからない
            AIMessage(content="資料からは見つかりませんでした。"),
        )
    )
    deps = make_deps(sessionmaker, redis, model)
    _, run = await start(sessionmaker, "q")
    await execute_run(deps, run.id)
    evs = await events(redis, run.id)
    done = evs[-1]
    # 差し戻した下書きは画面から消してから、書き直した回答を流す
    assert any(e["type"] == "answer.reset" for e in evs)
    # モデル自身の説明を残し、理由だけ付ける
    assert done["no_answer_reason"] == "no_relevant_sources"
    assert done["answer"] == "資料からは見つかりませんでした。"
    # 検索しただけの資料を出典として並べない
    assert done["citation_map"] == {} and done["sources"] == []


async def test_citations_renumbered_in_answer_order(
    sessionmaker: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    """検索した順の番号 [3][2] を、回答に出た順の [1][2] に振り直し、引用した箇所だけを残す。"""
    model = FakeToolModel(
        messages=script(tool_call("search", query="MX-17"), AIMessage(content="停止する[3]。点検は[2][3]。"))
    )
    search = FakeSearch("一つ目", "二つ目", "三つ目")
    deps = make_deps(sessionmaker, redis, model, search)
    _, run = await start(sessionmaker, "MX-17 は？")
    await execute_run(deps, run.id)
    done = (await events(redis, run.id))[-1]
    assert done["answer"] == "停止する[1]。点検は[2][1]。"
    by_section = {sec["id"]: sec for src in done["sources"] for sec in src["sections"]}
    assert set(done["citation_map"]) == {"1", "2"} and len(by_section) == 2
    assert by_section[done["citation_map"]["1"]["section_id"]]["body"] == "三つ目"
    assert by_section[done["citation_map"]["2"]["section_id"]]["body"] == "二つ目"
    async with sessionmaker() as s:
        cites = list(await s.scalars(select(Citation).where(Citation.message_id == run.message_id)))
        assert sorted((c.ordinal, c.snippet) for c in cites) == [(1, "三つ目"), (2, "二つ目")]


async def test_failed_models_are_named_with_reasons(
    sessionmaker: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    """主モデルも代替モデルも失敗したら、モデルごとの理由を回答欄と run.failed に出す。

    切り替えのステップも残す。
    """
    primary = FailingModel(messages=script(), error=ConnectionError("down"))
    backup = FailingModel(messages=script(), error=StatusError(402))
    deps = make_deps(sessionmaker, redis, primary)
    deps.resolve_models = lambda _id: ResolvedModels(
        id="qwen-chain", model=primary, fallback=backup, label="Qwen3 8B", fallback_label="DeepSeek"
    )
    _th, run = await start(sessionmaker, "MX-17 はどうする？")
    assert await execute_run(deps, run.id) == "failed"
    last = (await events(redis, run.id))[-1]
    assert last["type"] == "run.failed"
    assert (
        "Qwen3 8B: 接続できません" in last["message"]
        and "DeepSeek: 残高が不足しています（402）" in last["message"]
    )
    async with sessionmaker() as s:
        msg = await s.get(Message, run.message_id)
        assert msg is not None and "DeepSeek: 残高が不足" in msg.answer_text
        # 質問の整理・システムの最初の検索も記録に残る
        names = [st["name"] for st in msg.steps]
        assert names[:2] == ["understand", "search"] and names[-1] == "switch_model"


async def test_thinking_becomes_a_reasoning_step(
    sessionmaker: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    """本文の <think>…</think> は回答に入れず「思考プロセス」のステップにする。"""
    model = FakeToolModel(
        messages=script(
            tool_call("search", query="MX-17"),
            AIMessage(content="<think>\n資料 [1] によると即時停止。\n</think>\n\n即時停止です[1]。"),
        )
    )
    deps = make_deps(sessionmaker, redis, model)
    deps.resolve_models = lambda _id: ResolvedModels(id="qwen", model=model, label="Qwen3 8B")
    _th, run = await start(sessionmaker, "MX-17 はどうする？")
    assert await execute_run(deps, run.id) == "completed"
    evs = await events(redis, run.id)
    deltas = "".join(e["text"] for e in evs if e["type"] == "answer.delta")
    assert "think" not in deltas and "即時停止です" in deltas
    assert evs[-1]["answer"] == "即時停止です[1]。"
    async with sessionmaker() as s:
        msg = await s.get(Message, run.message_id)
        assert msg is not None and msg.answer_text == "即時停止です[1]。"
        r = next(st for st in msg.steps if st["name"] == "reasoning")
        assert r["status"] == "done" and r["output"] == {"reasoning": "資料 [1] によると即時停止。"}
        assert r["input"] == {"model": "Qwen3 8B"} and r["label"] == "思考プロセス"
