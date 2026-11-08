"""KB API（specs/003-ingestion B2・B3）。"""

import asyncio

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .conftest import ADMIN, ALICE, BOB, RecordingSync

pytestmark = pytest.mark.integration


async def test_personal_kb_created_once_under_concurrency(
    client: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    results = await asyncio.gather(*(client.get("/v1/kbs", headers=ALICE) for _ in range(10)))
    assert all(r.status_code == 200 for r in results)
    async with sessionmaker() as s:
        n = await s.scalar(text("SELECT count(*) FROM app.knowledge_bases WHERE owner_user_id = 'alice'"))
    assert n == 1
    kbs = results[0].json()
    assert [k["kind"] for k in kbs] == ["personal"]
    assert kbs[0]["writable"] is True


async def test_org_kb_lifecycle_and_visibility(
    client: httpx.AsyncClient, payload_sync: RecordingSync
) -> None:
    # member は作れない
    res = await client.post("/v1/kbs", json={"name": "全社規程"}, headers=ALICE)
    assert res.status_code == 403
    res = await client.post("/v1/kbs", json={"name": "全社規程"}, headers=ADMIN)
    assert res.status_code == 201
    kb = res.json()
    kb_id = kb["id"]
    assert kb["kind"] == "org" and kb["writable"] is True

    # member にも見えるが書込不可
    kbs = (await client.get("/v1/kbs", headers=ALICE)).json()
    org = next(k for k in kbs if k["id"] == kb_id)
    assert org["writable"] is False
    assert (await client.patch(f"/v1/kbs/{kb_id}", json={"name": "x"}, headers=ALICE)).status_code == 403

    # アーカイブ → 一覧に status=archived で残る
    synced = len(payload_sync.calls)
    res = await client.post(f"/v1/kbs/{kb_id}/archive", headers=ADMIN)
    assert res.json()["status"] == "archived"
    # アーカイブの切替では payload を同期しない（検索時のフィルタで扱う）
    assert len(payload_sync.calls) == synced
    assert (await client.post(f"/v1/kbs/{kb_id}/unarchive", headers=ADMIN)).json()["status"] == "active"

    # 削除 → 一覧から消える → 復元
    assert (await client.delete(f"/v1/kbs/{kb_id}", headers=ADMIN)).status_code == 204
    kbs = (await client.get("/v1/kbs", headers=ALICE)).json()
    assert all(k["id"] != kb_id for k in kbs)
    assert (await client.post(f"/v1/kbs/{kb_id}/restore", headers=ALICE)).status_code == 403
    assert (await client.post(f"/v1/kbs/{kb_id}/restore", headers=ADMIN)).status_code == 200


async def test_other_users_personal_kb_is_404_even_for_admin(client: httpx.AsyncClient) -> None:
    kbs = (await client.get("/v1/kbs", headers=BOB)).json()
    bob_kb = kbs[0]["id"]
    for headers in (ALICE, ADMIN):
        assert (
            await client.patch(f"/v1/kbs/{bob_kb}", json={"name": "x"}, headers=headers)
        ).status_code == 404
        assert (await client.get(f"/v1/kbs/{bob_kb}/folders", headers=headers)).status_code == 404
    # 個人 KB はアーカイブ・削除の対象外（本人でも 403）
    assert (await client.delete(f"/v1/kbs/{bob_kb}", headers=BOB)).status_code == 403


async def test_name_validation(client: httpx.AsyncClient) -> None:
    for name in ["", "   ", "a/b", "x" * 201]:
        res = await client.post("/v1/kbs", json={"name": name}, headers=ADMIN)
        assert res.status_code == 422, name
        assert res.json()["error"]["code"] == "invalid_request"


async def test_kb_audit_logged(
    client: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    kb_id = (await client.post("/v1/kbs", json={"name": "監査"}, headers=ADMIN)).json()["id"]
    await client.delete(f"/v1/kbs/{kb_id}", headers=ADMIN)
    await client.post(f"/v1/kbs/{kb_id}/restore", headers=ADMIN)
    async with sessionmaker() as s:
        actions = list(await s.scalars(text("SELECT action FROM app.audit_logs ORDER BY ts")))
    assert actions == ["kb.create", "kb.delete", "kb.restore"]
