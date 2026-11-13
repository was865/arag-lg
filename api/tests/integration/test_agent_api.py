"""対話 API（specs/005-agent C3・C4、R1〜R11・R26〜R32）。runner は動かさず、DB と Redis の状態で確かめる。"""

import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.agent.stream import EventSink, is_cancelled
from arag.db.models import Message, Run
from arag.settings import Settings

from .conftest import ALICE, BOB, as_user

pytestmark = pytest.mark.integration

MODELS = [
    {
        "id": "local",
        "label": "Qwen3 8B",
        "model": "openai:qwen3-8b",
        "base_url": "http://llm/v1",
        "tags": ["local"],
    },
    {"id": "nokey", "model": "nokey:some-model"},
]


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    r = Redis.from_url(Settings().redis_url, decode_responses=True)
    try:
        await r.ping()
    except Exception as e:
        pytest.skip(f"redis に接続できません: {e}")
    yield r
    await r.aclose()


@pytest.fixture
async def api(make_client: Callable[..., Awaitable[httpx.AsyncClient]], redis: Redis) -> httpx.AsyncClient:
    return await make_client(chat_models=MODELS, rate_limit_runs_per_min=0)


async def _ask(c: httpx.AsyncClient, q: str, thread_id: str | None = None, **kw: Any) -> dict[str, Any]:
    url = f"/v1/threads/{thread_id}/runs" if thread_id else "/v1/runs"
    r = await c.post(url, json={"query": q, **kw}, headers=ALICE)
    assert r.status_code == 202, r.text
    body: dict[str, Any] = r.json()
    return body


async def _finish(
    sm: async_sessionmaker[AsyncSession], run_id: str, ordinal: int, *, answer: str = "回答 [1]"
) -> str:
    """runner の代わりに run を完了させ、メッセージを保存する。"""
    async with sm() as s:
        run = await s.get(Run, uuid.UUID(run_id))
        assert run is not None
        run.status = "completed"
        msg = Message(
            id=run.message_id,
            thread_id=run.thread_id,
            ordinal=ordinal,
            query=run.request["query"],
            answer_text=answer,
            model_id=run.model_id,
            steps=[{"id": "c1", "name": "search", "label": "検索", "status": "done"}],
            sources=[],
            citation_map={"1": {"source_id": "s1", "section_id": "x1"}},
            checkpoint_id=f"ckpt-{ordinal}",
            run_id=run.id,
            suggestions=["次の質問は？"],
        )
        s.add(msg)
        await s.commit()
        return str(msg.id)


async def test_models_lists_availability(api: httpx.AsyncClient) -> None:
    r = await api.get("/v1/models", headers=ALICE)
    assert r.status_code == 200
    body = r.json()
    assert body["default_id"] == "local"
    assert [(m["id"], m["available"]) for m in body["models"]] == [("local", True), ("nokey", False)]


async def test_thread_crud_and_isolation(api: httpx.AsyncClient) -> None:
    r = await api.post("/v1/threads", json={}, headers=ALICE)
    assert r.status_code == 201
    tid = r.json()["id"]
    assert r.json()["title"] == "新しいチャット"

    r = await api.patch(f"/v1/threads/{tid}", json={"title": "設備の質問", "pinned": True}, headers=ALICE)
    assert r.json()["title"] == "設備の質問" and r.json()["pinned"] is True

    r = await api.get("/v1/threads", headers=ALICE)
    assert [t["id"] for t in r.json()["items"]] == [tid]
    assert (await api.get("/v1/threads", headers=BOB)).json()["items"] == []

    # 他人のスレッドは見えない・変えられない・消せない
    assert (await api.get(f"/v1/threads/{tid}", headers=BOB)).status_code == 404
    assert (await api.patch(f"/v1/threads/{tid}", json={"pinned": False}, headers=BOB)).status_code == 404
    assert (await api.delete(f"/v1/threads/{tid}", headers=BOB)).status_code == 404

    assert (await api.delete(f"/v1/threads/{tid}", headers=ALICE)).status_code == 204
    assert (await api.get(f"/v1/threads/{tid}", headers=ALICE)).status_code == 404


async def test_run_creates_thread_and_blocks_second_run(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    created = await _ask(api, "  MX-17 の異常時の対応は？\n詳しく  ")
    tid = created["thread_id"]

    detail = (await api.get(f"/v1/threads/{tid}", headers=ALICE)).json()
    assert detail["title"] == "MX-17 の異常時の対応は？ 詳しく"
    assert detail["messages"] == []
    assert detail["active_run"]["run_id"] == created["run_id"]
    assert detail["active_run"]["query"] == "MX-17 の異常時の対応は？\n詳しく"

    r = await api.get(f"/v1/threads/{tid}/active-run", headers=ALICE)
    assert r.status_code == 200 and r.json()["message_id"] == created["message_id"]

    # 同じスレッドで回答中なら 409
    r = await api.post(f"/v1/threads/{tid}/runs", json={"query": "次は？"}, headers=ALICE)
    assert r.status_code == 409 and r.json()["error"]["code"] == "run_in_progress"

    async with sessionmaker() as s:
        run = await s.get(Run, uuid.UUID(created["run_id"]))
        assert run is not None
        assert run.model_id == "local"
        assert run.request["ordinal"] == 1 and run.request["branch"] is False
        assert run.request["principal"]["user_id"] == "alice"

    await _finish(sessionmaker, created["run_id"], 1)
    assert (await api.get(f"/v1/threads/{tid}/active-run", headers=ALICE)).status_code == 204

    second = await _ask(api, "次は？", tid)
    async with sessionmaker() as s:
        run = await s.get(Run, uuid.UUID(second["run_id"]))
        assert run is not None and run.request["ordinal"] == 2


async def test_thread_detail_returns_messages_and_feedback(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    created = await _ask(api, "質問")
    mid = await _finish(sessionmaker, created["run_id"], 1)

    r = await api.put(
        f"/v1/messages/{mid}/feedback",
        json={"rating": "down", "reason_tags": ["wrong"], "comment": "別の章です"},
        headers=ALICE,
    )
    assert r.status_code == 200
    # 上書きできる
    r = await api.put(f"/v1/messages/{mid}/feedback", json={"rating": "up"}, headers=ALICE)
    assert r.json() == {"rating": "up", "reason_tags": [], "comment": None}
    assert (
        await api.put(f"/v1/messages/{mid}/feedback", json={"rating": "up"}, headers=BOB)
    ).status_code == 404

    detail = (await api.get(f"/v1/threads/{created['thread_id']}", headers=ALICE)).json()
    [m] = detail["messages"]
    assert m["answer"] == "回答 [1]"
    assert m["steps"][0]["label"] == "検索"
    assert m["citation_map"]["1"]["section_id"] == "x1"
    assert m["feedback"]["rating"] == "up"
    # 続けて聞く質問の候補も履歴から戻せる（specs/028 R6）
    assert m["suggestions"] == ["次の質問は？"]
    assert detail["active_run"] is None


async def test_branch_from_message_reuses_ordinal_and_checkpoint(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    first = await _ask(api, "一つ目")
    tid = first["thread_id"]
    await _finish(sessionmaker, first["run_id"], 1)
    second = await _ask(api, "二つ目", tid)
    mid2 = await _finish(sessionmaker, second["run_id"], 2)

    edited = await _ask(api, "二つ目（直した）", tid, from_message_id=mid2)
    async with sessionmaker() as s:
        run = await s.get(Run, uuid.UUID(edited["run_id"]))
        assert run is not None
        assert run.request["ordinal"] == 2
        assert run.request["branch"] is True
        assert run.request["branch_checkpoint_id"] == "ckpt-2"

    # 別スレッドのメッセージからは分岐できない
    other = await _ask(api, "別スレッド")
    r = await api.post(
        f"/v1/threads/{other['thread_id']}/runs", json={"query": "x", "from_message_id": mid2}, headers=ALICE
    )
    assert r.status_code == 404


async def test_unverified_user_cannot_start_run(api: httpx.AsyncClient) -> None:
    r = await api.post("/v1/runs", json={"query": "q"}, headers=ALICE | {"X-Dev-Email-Verified": "false"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "email_not_verified"


async def test_validation_and_unavailable_model(api: httpx.AsyncClient) -> None:
    assert (await api.post("/v1/runs", json={"query": "   "}, headers=ALICE)).status_code == 422
    assert (await api.post("/v1/runs", json={"query": "あ" * 4001}, headers=ALICE)).status_code == 422
    r = await api.post("/v1/runs", json={"query": "q", "model_id": "nokey"}, headers=ALICE)
    assert r.status_code == 422 and r.json()["error"]["code"] == "model_unavailable"
    r = await api.post("/v1/runs", json={"query": "q", "model_id": "missing"}, headers=ALICE)
    assert r.json()["error"]["code"] == "model_unavailable"


async def test_stream_replays_and_resumes_from_last_event_id(
    api: httpx.AsyncClient, redis: Redis, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    created = await _ask(api, "質問")
    rid, mid = created["run_id"], created["message_id"]
    sink = EventSink(redis, rid, ttl_sec=60)
    await sink.emit(
        {
            "type": "run.started",
            "run_id": rid,
            "message_id": mid,
            "thread_id": created["thread_id"],
            "model_id": "local",
        }
    )
    await sink.emit({"type": "answer.delta", "message_id": mid, "text": "こんにちは"})
    await sink.flush()
    await sink.emit(
        {
            "type": "run.completed",
            "message_id": mid,
            "answer": "こんにちは",
            "tokens_in": 1,
            "tokens_out": 2,
            "duration_ms": 3,
            "citation_map": {},
            "sources": [],
        }
    )

    r = await api.get(f"/v1/runs/{rid}/stream", headers=ALICE)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(r.text)
    assert [e["event"] for e in events] == ["run.started", "answer.delta", "run.completed"]
    assert json.loads(events[1]["data"])["text"] == "こんにちは"

    r = await api.get(f"/v1/runs/{rid}/stream", headers={**ALICE, "Last-Event-ID": events[1]["id"]})
    assert [e["event"] for e in _parse_sse(r.text)] == ["run.completed"]

    assert (await api.get(f"/v1/runs/{rid}/stream", headers=BOB)).status_code == 404

    # 終わってストリームも消えたら 410
    await _finish(sessionmaker, rid, 1)
    await redis.delete(f"run:{rid}:events")
    r = await api.get(f"/v1/runs/{rid}/stream", headers=ALICE)
    assert r.status_code == 410 and r.json()["error"]["code"] == "run_expired"


async def test_cancel_queued_run_emits_event(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    created = await _ask(api, "質問")
    rid = created["run_id"]
    assert (await api.post(f"/v1/runs/{rid}/cancel", headers=BOB)).status_code == 404
    assert (await api.post(f"/v1/runs/{rid}/cancel", headers=ALICE)).status_code == 202
    async with sessionmaker() as s:
        run = await s.get(Run, uuid.UUID(rid))
        assert run is not None and run.status == "cancelled"
    r = await api.get(f"/v1/runs/{rid}/stream", headers=ALICE)
    assert [e["event"] for e in _parse_sse(r.text)] == ["run.cancelled"]
    # 取り消したので次の質問ができる
    await _ask(api, "次", created["thread_id"])


async def test_cancel_running_run_sets_flag(
    api: httpx.AsyncClient, redis: Redis, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    created = await _ask(api, "質問")
    rid = created["run_id"]
    async with sessionmaker() as s:
        run = await s.get(Run, uuid.UUID(rid))
        assert run is not None
        run.status = "running"
        await s.commit()
    assert (await api.post(f"/v1/runs/{rid}/cancel", headers=ALICE)).status_code == 202
    assert await is_cancelled(redis, rid)


async def test_rate_limit_per_minute(
    make_client: Callable[..., Awaitable[httpx.AsyncClient]], redis: Redis
) -> None:
    c = await make_client(chat_models=MODELS, rate_limit_runs_per_min=2)
    who = as_user(f"rl-{uuid.uuid4().hex[:8]}")
    codes = [(await c.post("/v1/runs", json={"query": f"q{i}"}, headers=who)).status_code for i in range(3)]
    assert codes == [202, 202, 429]


async def test_monthly_token_limit(
    make_client: Callable[..., Awaitable[httpx.AsyncClient]],
    redis: Redis,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    c = await make_client(chat_models=MODELS, rate_limit_runs_per_min=0, monthly_token_limit=100)
    created = await _ask(c, "質問")
    await _finish(sessionmaker, created["run_id"], 1)
    async with sessionmaker() as s:
        msg = (await s.scalars(select(Message))).one()
        msg.tokens_in, msg.tokens_out = 80, 30
        await s.commit()
    r = await c.post("/v1/runs", json={"query": "もう一つ"}, headers=ALICE)
    assert r.status_code == 429 and r.json()["error"]["code"] == "monthly_quota_exceeded"
    # 他の人は使える
    assert (await c.post("/v1/runs", json={"query": "q"}, headers=BOB)).status_code == 202


def _parse_sse(text: str) -> list[dict[str, str]]:
    out = []
    for block in text.split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if line.startswith(":") or ":" not in line:
                continue
            k, _, v = line.partition(":")
            fields[k] = v.removeprefix(" ")
        if "event" in fields:
            out.append(fields)
    return out


async def test_thread_search_matches_title_question_and_answer(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    """スレッドの検索（specs/022 R1）: 題名・質問・回答の本文を探し、自分のスレッドだけを返す。"""
    a = await _ask(api, "MX-17 の異常時の対応は？")
    answer_a = "直ちに設備を停止し、保全課（内線 2417）に連絡します [1]。"
    await _finish(sessionmaker, a["run_id"], 1, answer=answer_a)
    b = await _ask(api, "年次点検はいつ？")
    await _finish(sessionmaker, b["run_id"], 1, answer="毎年8月の夏季休業中です [1]。")
    await api.patch(f"/v1/threads/{b['thread_id']}", json={"title": "点検の予定"}, headers=ALICE)

    def ids(r: httpx.Response) -> list[str]:
        assert r.status_code == 200, r.text
        return [h["thread"]["id"] for h in r.json()["items"]]

    # 回答の本文
    r = await api.get("/v1/threads/search", params={"q": "内線 2417"}, headers=ALICE)
    assert ids(r) == [a["thread_id"]]
    [hit] = r.json()["items"]
    assert hit["match"] == "answer" and "2417" in hit["snippet"]
    assert hit["message_id"] is not None
    # 質問（大文字・小文字を区別しない）
    assert ids(await api.get("/v1/threads/search", params={"q": "mx-17"}, headers=ALICE)) == [a["thread_id"]]
    # 題名
    r = await api.get("/v1/threads/search", params={"q": "点検の予定"}, headers=ALICE)
    assert ids(r) == [b["thread_id"]] and r.json()["items"][0]["match"] == "title"
    # 空白で区切った語はすべて含む（AND）
    found = await api.get("/v1/threads/search", params={"q": "8月 夏季"}, headers=ALICE)
    assert ids(found) == [b["thread_id"]]
    assert ids(await api.get("/v1/threads/search", params={"q": "8月 MX-17"}, headers=ALICE)) == []
    # LIKE の記号はそのままの文字として探す
    assert ids(await api.get("/v1/threads/search", params={"q": "%"}, headers=ALICE)) == []
    # 他人のスレッドは出ない
    assert ids(await api.get("/v1/threads/search", params={"q": "2417"}, headers=BOB)) == []
    # 空の語は 422
    assert (await api.get("/v1/threads/search", params={"q": "  "}, headers=ALICE)).status_code == 422
