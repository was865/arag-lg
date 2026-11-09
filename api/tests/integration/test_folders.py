"""フォルダ API（specs/003-ingestion B4・R32・R33）。"""

import uuid

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .conftest import ALICE, BOB, RecordingSync

pytestmark = pytest.mark.integration


async def _personal_kb(client: httpx.AsyncClient, headers: dict[str, str]) -> str:
    kbs = (await client.get("/v1/kbs", headers=headers)).json()
    return str(next(k for k in kbs if k["kind"] == "personal")["id"])


async def _mk(client: httpx.AsyncClient, kb: str, name: str, parent: str | None = None) -> str:
    res = await client.post(f"/v1/kbs/{kb}/folders", json={"name": name, "parent_id": parent}, headers=ALICE)
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


async def test_create_list_and_conflict(client: httpx.AsyncClient) -> None:
    kb = await _personal_kb(client, ALICE)
    a = await _mk(client, kb, "規程")
    await _mk(client, kb, "細則", a)
    # 同じ親・同名は 409、別の親なら可
    res = await client.post(f"/v1/kbs/{kb}/folders", json={"name": "規程"}, headers=ALICE)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "folder_name_conflict"
    await _mk(client, kb, "規程", a)
    names = sorted(f["name"] for f in (await client.get(f"/v1/kbs/{kb}/folders", headers=ALICE)).json())
    assert names == ["細則", "規程", "規程"]
    # 他人の KB には作れない（404）
    res = await client.post(f"/v1/kbs/{kb}/folders", json={"name": "x"}, headers=BOB)
    assert res.status_code == 404


async def test_move_and_cycle(client: httpx.AsyncClient) -> None:
    kb = await _personal_kb(client, ALICE)
    a = await _mk(client, kb, "A")
    b = await _mk(client, kb, "B", a)
    c = await _mk(client, kb, "C", b)
    # 自分の子孫の下へは 400
    for target in (a, b, c):
        res = await client.patch(f"/v1/folders/{a}", json={"parent_id": target}, headers=ALICE)
        assert res.status_code == 400, target
    # ルートへ移動（parent_id を明示的に null）
    res = await client.patch(f"/v1/folders/{c}", json={"parent_id": None}, headers=ALICE)
    assert res.status_code == 200 and res.json()["parent_id"] is None
    # 名前だけの変更は移動しない
    res = await client.patch(f"/v1/folders/{b}", json={"name": "B2"}, headers=ALICE)
    assert res.json()["parent_id"] == a and res.json()["name"] == "B2"
    # 存在しない親
    res = await client.patch(f"/v1/folders/{b}", json={"parent_id": str(uuid.uuid4())}, headers=ALICE)
    assert res.status_code == 400


async def _add_doc(s: AsyncSession, kb: str, folder: str, h: str) -> None:
    await s.execute(
        text(
            "INSERT INTO app.contents (content_hash, mime, ext, size, status, ref_count) "
            "VALUES (:h, 'text/plain', 'txt', 1, 'ready', 1)"
        ),
        {"h": h},
    )
    await s.execute(
        text(
            "INSERT INTO app.documents (id, kb_id, content_hash, folder_id, filename, uploaded_by) "
            "VALUES (:id, :kb, :h, :f, 'a.txt', 'alice')"
        ),
        {"id": uuid.uuid4(), "kb": kb, "h": h, "f": folder},
    )


async def test_trash_recursive_and_restore_revives_ancestors(
    client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    payload_sync: RecordingSync,
) -> None:
    kb = await _personal_kb(client, ALICE)
    a = await _mk(client, kb, "A")
    b = await _mk(client, kb, "B", a)
    c = await _mk(client, kb, "C", b)
    sibling = await _mk(client, kb, "S", a)
    async with sessionmaker() as s:
        await _add_doc(s, kb, c, "c" * 64)
        await _add_doc(s, kb, sibling, "d" * 64)
        await s.commit()

    # B を消すと C と C の文書も消える
    assert (await client.delete(f"/v1/folders/{b}", headers=ALICE)).status_code == 204
    assert payload_sync.calls[-1] == {"c" * 64}
    live = {f["name"] for f in (await client.get(f"/v1/kbs/{kb}/folders", headers=ALICE)).json()}
    assert live == {"A", "S"}

    # 次に A を消す（S と S の文書が消える）
    assert (await client.delete(f"/v1/folders/{a}", headers=ALICE)).status_code == 204
    # C だけを復元 → 祖先 A・B も復活。ただし A と同時に消えた S は戻らない
    res = await client.post(f"/v1/folders/{c}/restore", headers=ALICE)
    assert res.status_code == 200, res.text
    live = {f["name"] for f in (await client.get(f"/v1/kbs/{kb}/folders", headers=ALICE)).json()}
    assert live == {"A", "B", "C"}
    async with sessionmaker() as s:
        rows = dict(
            (await s.execute(text("SELECT content_hash, deleted_at IS NULL FROM app.documents"))).all()
        )
    assert rows == {"c" * 64: True, "d" * 64: False}
    async with sessionmaker() as s:
        actions = list(await s.scalars(text("SELECT action FROM app.audit_logs ORDER BY ts")))
    assert actions == ["folder.delete", "folder.delete", "folder.restore"]


async def test_restore_name_conflict_is_409(client: httpx.AsyncClient) -> None:
    kb = await _personal_kb(client, ALICE)
    a = await _mk(client, kb, "A")
    await client.delete(f"/v1/folders/{a}", headers=ALICE)
    await _mk(client, kb, "A")
    res = await client.post(f"/v1/folders/{a}/restore", headers=ALICE)
    assert res.status_code == 409


async def test_purge_folder_removes_subtree_and_orphans(
    client: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    """フォルダをごみ箱から完全に削除する（配下のフォルダ・文書ごと。文書と同じ権限）。"""
    kb = await _personal_kb(client, ALICE)
    a = await _mk(client, kb, "A")
    b = await _mk(client, kb, "B", a)
    keep = await _mk(client, kb, "K")
    async with sessionmaker() as s:
        await _add_doc(s, kb, a, "1" * 64)
        await _add_doc(s, kb, b, "2" * 64)
        await _add_doc(s, kb, keep, "3" * 64)
        await s.commit()

    # 生きているフォルダは完全削除できない（404）
    assert (await client.delete(f"/v1/folders/{a}/purge", headers=ALICE)).status_code == 404
    assert (await client.delete(f"/v1/folders/{a}", headers=ALICE)).status_code == 204
    trash = (await client.get("/v1/trash", headers=ALICE)).json()
    item = next(t for t in trash if t["kind"] == "folder")
    assert item["id"] == a and item["purgeable"] is True
    # 他人は消せない
    assert (await client.delete(f"/v1/folders/{a}/purge", headers=BOB)).status_code == 404

    assert (await client.delete(f"/v1/folders/{a}/purge", headers=ALICE)).status_code == 204
    async with sessionmaker() as s:
        folders = set(await s.scalars(text("SELECT name FROM app.folders")))
        docs = set(await s.scalars(text("SELECT content_hash FROM app.documents")))
        contents = set(await s.scalars(text("SELECT content_hash FROM app.contents")))
        audit = await s.scalar(text("SELECT detail::text FROM app.audit_logs WHERE action='folder.purge'"))
    assert folders == {"K"}
    assert docs == {"3" * 64} and contents == {"3" * 64}
    assert audit is not None and '"documents": 2' in audit and '"folders": 2' in audit
    assert (await client.get("/v1/trash", headers=ALICE)).json() == []


async def test_purge_folder_grace_period(
    client: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    kb = await _personal_kb(client, ALICE)
    a = await _mk(client, kb, "A")
    async with sessionmaker() as s:
        await _add_doc(s, kb, a, "4" * 64)
        await s.commit()
    await client.delete(f"/v1/folders/{a}", headers=ALICE)
    async with sessionmaker() as s:
        await s.execute(text("UPDATE app.folders SET deleted_at = deleted_at - interval '2 days'"))
        await s.execute(text("UPDATE app.documents SET deleted_at = deleted_at - interval '2 days'"))
        await s.commit()
    item = (await client.get("/v1/trash", headers=ALICE)).json()[0]
    assert item["purgeable"] is False
    assert (await client.delete(f"/v1/folders/{a}/purge", headers=ALICE)).status_code == 403
