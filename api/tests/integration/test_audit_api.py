"""監査ログの一覧と member.* の書き込み（specs/011-audit-log A1、R1〜R3）。"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.db.models import AuditLog

from .conftest import ADMIN, ALICE

pytestmark = pytest.mark.integration


@pytest.fixture
async def api(make_client: Callable[..., Awaitable[httpx.AsyncClient]]) -> httpx.AsyncClient:
    return await make_client()


async def _seed(sm: async_sessionmaker[AsyncSession]) -> None:
    now = datetime.now(UTC)
    async with sm() as s:
        for i, (action, actor, email) in enumerate(
            [
                ("document.delete", "alice", "alice@x.test"),
                ("document.restore", "alice", "alice@x.test"),
                ("kb.create", "admin1", "admin@x.test"),
                ("thread.share", "bob", "bob@x.test"),
            ]
        ):
            s.add(
                AuditLog(
                    ts=now - timedelta(minutes=10 - i),
                    actor_id=actor,
                    actor_email=email,
                    action=action,
                    resource_type=action.split(".")[0],
                    resource_id=f"r{i}",
                    result="ok",
                    detail={"i": i},
                )
            )
        await s.commit()


async def test_only_admins_can_list(api: httpx.AsyncClient) -> None:
    assert (await api.get("/v1/admin/audit", headers=ALICE)).status_code == 403
    assert (await api.get("/v1/admin/audit", headers=ADMIN)).status_code == 200


async def test_list_filters_and_cursor(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _seed(sessionmaker)
    body = (await api.get("/v1/admin/audit", headers=ADMIN)).json()
    assert [x["action"] for x in body["items"]] == [
        "thread.share",
        "kb.create",
        "document.restore",
        "document.delete",
    ]
    assert body["items"][0]["actor_email"] == "bob@x.test" and body["items"][0]["detail"] == {"i": 3}

    r = await api.get("/v1/admin/audit", params={"action": "document."}, headers=ADMIN)
    assert [x["action"] for x in r.json()["items"]] == ["document.restore", "document.delete"]
    r = await api.get("/v1/admin/audit", params={"actor": "ALICE@"}, headers=ADMIN)
    assert len(r.json()["items"]) == 2
    since = (datetime.now(UTC) - timedelta(minutes=8, seconds=30)).isoformat()
    r = await api.get("/v1/admin/audit", params={"from": since}, headers=ADMIN)
    assert [x["action"] for x in r.json()["items"]] == ["thread.share", "kb.create"]

    # 2 件ずつ送る
    page1 = (await api.get("/v1/admin/audit", params={"limit": 2}, headers=ADMIN)).json()
    assert len(page1["items"]) == 2 and page1["next_cursor"]
    page2 = (
        await api.get("/v1/admin/audit", params={"limit": 2, "cursor": page1["next_cursor"]}, headers=ADMIN)
    ).json()
    assert [x["action"] for x in page2["items"]] == ["document.restore", "document.delete"]
    assert page2["next_cursor"] is None
    assert (await api.get("/v1/admin/audit", params={"cursor": "bad"}, headers=ADMIN)).status_code == 422


async def test_write_member_events_only(api: httpx.AsyncClient) -> None:
    ok = {"action": "member.ban", "resource_id": "u1", "detail": {"reason": "x"}}
    assert (await api.post("/v1/admin/audit", json=ok, headers=ALICE)).status_code == 403
    r = await api.post("/v1/admin/audit", json=ok, headers=ADMIN)
    assert r.status_code == 201
    bad = {"action": "document.delete", "resource_id": "d"}
    assert (await api.post("/v1/admin/audit", json=bad, headers=ADMIN)).status_code == 422

    [row] = (await api.get("/v1/admin/audit", params={"action": "member."}, headers=ADMIN)).json()["items"]
    assert row["actor_id"] == "admin1" and row["resource_type"] == "user" and row["resource_id"] == "u1"
