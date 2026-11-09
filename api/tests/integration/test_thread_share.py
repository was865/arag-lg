"""スレッドの共有（specs/008-thread-share A2、R1〜R5・R8）。"""

import uuid
from collections.abc import Awaitable, Callable

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.db.models import AuditLog, Message, Thread

from .conftest import ALICE, BOB

pytestmark = pytest.mark.integration


@pytest.fixture
async def api(make_client: Callable[..., Awaitable[httpx.AsyncClient]]) -> httpx.AsyncClient:
    return await make_client()


async def _thread_with_answer(api: httpx.AsyncClient, sm: async_sessionmaker[AsyncSession]) -> str:
    tid = (await api.post("/v1/threads", json={"title": "設備の質問"}, headers=ALICE)).json()["id"]
    async with sm() as s:
        s.add(
            Message(
                id=uuid.uuid4(),
                thread_id=uuid.UUID(tid),
                ordinal=1,
                query="MX-17 は止めますか",
                answer_text="夜間まで運転できます [1]",
                tokens_in=1200,
                steps=[{"id": "c1", "name": "search", "label": "検索", "status": "done"}],
                sources=[
                    {
                        "id": "doc-1",
                        "title": "点検台帳.pdf",
                        "sections": [
                            {
                                "id": "x1",
                                "n": 1,
                                "heading": "判定",
                                "body": "秘密の本文",
                                "block_type": "text",
                            }
                        ],
                    }
                ],
                citation_map={"1": {"source_id": "doc-1", "section_id": "x1"}},
            )
        )
        s.add(Message(id=uuid.uuid4(), thread_id=uuid.UUID(tid), ordinal=2, query="途中", status="running"))
        await s.commit()
    return tid


async def test_visibility_issues_token_and_keeps_it(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    tid = await _thread_with_answer(api, sessionmaker)
    detail = (await api.get(f"/v1/threads/{tid}", headers=ALICE)).json()
    assert detail["visibility"] == "private" and detail["share_token"] is None

    r = await api.patch(f"/v1/threads/{tid}", json={"visibility": "org"}, headers=ALICE)
    assert r.status_code == 200
    token = r.json()["share_token"]
    assert r.json()["visibility"] == "org" and len(token) >= 22

    # private に戻してもトークンは保つ。再公開で同じリンク
    r = await api.patch(f"/v1/threads/{tid}", json={"visibility": "private"}, headers=ALICE)
    assert r.json()["share_token"] == token
    r = await api.patch(f"/v1/threads/{tid}", json={"visibility": "public"}, headers=ALICE)
    assert r.json()["share_token"] == token
    assert (await api.get("/v1/threads", headers=ALICE)).json()["items"][0]["visibility"] == "public"

    # 他人は変えられない。不正な値は 422
    assert (await api.patch(f"/v1/threads/{tid}", json={"visibility": "org"}, headers=BOB)).status_code == 404
    assert (
        await api.patch(f"/v1/threads/{tid}", json={"visibility": "all"}, headers=ALICE)
    ).status_code == 422

    async with sessionmaker() as s:
        rows = list(await s.scalars(select(AuditLog).where(AuditLog.action == "thread.share")))
    assert [r.detail["visibility"] for r in rows] == ["org", "private", "public"]


async def test_shared_access_by_visibility(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    tid = await _thread_with_answer(api, sessionmaker)
    token = (await api.patch(f"/v1/threads/{tid}", json={"visibility": "org"}, headers=ALICE)).json()[
        "share_token"
    ]

    # org: ログインしていれば誰でも、未ログインは 401
    assert (await api.get(f"/v1/shared/{token}", headers=BOB)).status_code == 200
    r = await api.get(f"/v1/shared/{token}")
    assert r.status_code == 401

    # public: 未ログインでも読める。返すのは最小限
    await api.patch(f"/v1/threads/{tid}", json={"visibility": "public"}, headers=ALICE)
    r = await api.get(f"/v1/shared/{token}")
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "title": "設備の質問",
        "visibility": "public",
        "messages": [
            {
                "query": "MX-17 は止めますか",
                "answer": "夜間まで運転できます [1]",
                "created_at": body["messages"][0]["created_at"],
                "sources": [{"n": 1, "title": "点検台帳.pdf", "heading": "判定", "page": None}],
                "has_image": False,
            }
        ],
    }

    # private と存在しないトークンは同じ 404
    await api.patch(f"/v1/threads/{tid}", json={"visibility": "private"}, headers=ALICE)
    for t in (token, "x" * 22):
        r = await api.get(f"/v1/shared/{t}", headers=BOB)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"


async def test_shared_token_is_unique_per_thread(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    a = await _thread_with_answer(api, sessionmaker)
    b = await _thread_with_answer(api, sessionmaker)
    ta = (await api.patch(f"/v1/threads/{a}", json={"visibility": "public"}, headers=ALICE)).json()[
        "share_token"
    ]
    tb = (await api.patch(f"/v1/threads/{b}", json={"visibility": "public"}, headers=ALICE)).json()[
        "share_token"
    ]
    assert ta != tb
    async with sessionmaker() as s:
        t = await s.get(Thread, uuid.UUID(a))
        assert t is not None and t.share_token == ta
