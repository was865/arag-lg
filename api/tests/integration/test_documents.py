"""文書・参照・ごみ箱 API（specs/003-ingestion F1〜F4、R31〜R38）。"""

import uuid
from collections.abc import Awaitable, Callable

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.ingest.index import QdrantIndex
from arag.ingest.pipeline import run_ingest

from .conftest import ADMIN, ALICE, BOB, RecordingSync, as_user
from .ingest_helpers import make_deps
from .test_ingest import MD, _personal, _upload

pytestmark = pytest.mark.integration


async def _ingested(
    client: httpx.AsyncClient,
    sm: async_sessionmaker[AsyncSession],
    index: QdrantIndex,
    root: str,
    files: list[tuple[str, bytes]],
    headers: dict[str, str] = ALICE,
    kb: str | None = None,
) -> tuple[str, list[dict[str, str]]]:
    kb = kb or await _personal(client, headers)
    items = (await _upload(client, kb, files, headers)).json()["items"]
    deps = make_deps(sm, root, index)
    for i in items:
        if i["job_id"]:
            await run_ingest(uuid.UUID(i["job_id"]), deps)
    return kb, items


async def test_list_filters_cursor_and_stats(client: httpx.AsyncClient) -> None:
    kb = await _personal(client, ALICE)
    folder = (await client.post(f"/v1/kbs/{kb}/folders", json={"name": "F"}, headers=ALICE)).json()["id"]
    await _upload(client, kb, [(f"{i}.txt", f"本文{i}".encode()) for i in range(5)])
    await _upload(client, kb, [("in.txt", b"in-folder")], paths=None)
    in_folder = (await client.get(f"/v1/documents?kb_id={kb}", headers=ALICE)).json()["items"][0]
    await client.patch(f"/v1/documents/{in_folder['id']}", json={"folder_id": folder}, headers=ALICE)

    seen: list[str] = []
    cursor = None
    while True:
        url = f"/v1/documents?kb_id={kb}&limit=2" + (f"&cursor={cursor}" if cursor else "")
        page = (await client.get(url, headers=ALICE)).json()
        seen += [d["id"] for d in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 6
    items = (await client.get(f"/v1/documents?folder_id={folder}", headers=ALICE)).json()["items"]
    assert [d["filename"] for d in items] == ["in.txt"]
    root = (await client.get(f"/v1/documents?kb_id={kb}&root_only=true", headers=ALICE)).json()["items"]
    assert len(root) == 5
    queued = (await client.get(f"/v1/documents?kb_id={kb}&status=queued", headers=ALICE)).json()["items"]
    assert len(queued) == 6 and queued[0]["writable"] is True and queued[0]["job_id"]
    # status はカンマ区切りで複数指定できる。q はファイル名の部分一致（大文字小文字・% _ はそのまま）
    base = f"/v1/documents?kb_id={kb}"
    assert len((await client.get(f"{base}&status=running,queued", headers=ALICE)).json()["items"]) == 6
    assert (await client.get(f"{base}&status=error,cancelled", headers=ALICE)).json()["items"] == []
    named = (await client.get(f"/v1/documents?kb_id={kb}&q=IN.T", headers=ALICE)).json()["items"]
    assert [d["filename"] for d in named] == ["in.txt"]
    assert (await client.get(f"/v1/documents?kb_id={kb}&q=%25", headers=ALICE)).json()["items"] == []
    stats = (await client.get("/v1/documents/stats", headers=ALICE)).json()
    assert stats["documents"] == 6 and stats["by_status"] == {"queued": 6}
    # 他人からは見えない
    assert (await client.get("/v1/documents", headers=BOB)).json()["items"] == []
    assert (await client.get(f"/v1/documents/{in_folder['id']}", headers=BOB)).status_code == 404


async def test_rename_move_bulk(client: httpx.AsyncClient) -> None:
    kb = await _personal(client, ALICE)
    f = (await client.post(f"/v1/kbs/{kb}/folders", json={"name": "F"}, headers=ALICE)).json()["id"]
    items = (await _upload(client, kb, [("a.txt", b"a"), ("b.txt", b"b")])).json()["items"]
    ids = [i["document_id"] for i in items]
    res = await client.patch(f"/v1/documents/{ids[0]}", json={"filename": "新しい名前.txt"}, headers=ALICE)
    assert res.json()["filename"] == "新しい名前.txt" and res.json()["folder_id"] is None
    res = await client.post("/v1/documents/bulk-move", json={"ids": ids, "folder_id": f}, headers=ALICE)
    assert res.json() == {"updated": 2}
    res = await client.patch(f"/v1/documents/{ids[0]}", json={"folder_id": None}, headers=ALICE)
    assert res.json()["folder_id"] is None
    # 別 KB のフォルダへは移せない
    bob_kb = await _personal(client, BOB)
    bf = (await client.post(f"/v1/kbs/{bob_kb}/folders", json={"name": "B"}, headers=BOB)).json()["id"]
    assert (
        await client.patch(f"/v1/documents/{ids[0]}", json={"folder_id": bf}, headers=ALICE)
    ).status_code == 400
    # 1 件でも権限外なら一括操作全体が 404
    res = await client.post("/v1/documents/bulk-delete", json={"ids": ids}, headers=BOB)
    assert res.status_code == 404


async def test_delete_restore_revives_folder_and_syncs_payload(
    client: httpx.AsyncClient, payload_sync: RecordingSync, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    kb = await _personal(client, ALICE)
    item = (await _upload(client, kb, [("a.txt", b"a")], paths=["F/a.txt"])).json()["items"][0]
    doc = item["document_id"]
    folder = (await client.get(f"/v1/kbs/{kb}/folders", headers=ALICE)).json()[0]["id"]
    assert (await client.delete(f"/v1/documents/{doc}", headers=ALICE)).status_code == 204
    await client.delete(f"/v1/folders/{folder}", headers=ALICE)
    assert (await client.get(f"/v1/documents/{doc}", headers=ALICE)).status_code == 404
    calls_before = len(payload_sync.calls)
    res = await client.post(f"/v1/documents/{doc}/restore", headers=ALICE)
    assert res.status_code == 200 and res.json()["folder_id"] == folder
    assert len(payload_sync.calls) == calls_before + 1
    assert [f["id"] for f in (await client.get(f"/v1/kbs/{kb}/folders", headers=ALICE)).json()] == [folder]
    async with sessionmaker() as s:
        actions = list(await s.scalars(text("SELECT action FROM app.audit_logs ORDER BY ts")))
    assert actions == ["document.delete", "folder.delete", "document.restore"]


async def test_purge_rules_and_orphan_cleanup(
    make_client: Callable[..., Awaitable[httpx.AsyncClient]],
    sessionmaker: async_sessionmaker[AsyncSession],
    qdrant_index: QdrantIndex,
    storage_root: str,
) -> None:
    client = await make_client(index=qdrant_index)
    _, items = await _ingested(client, sessionmaker, qdrant_index, storage_root, [("a.md", MD.encode())])
    doc = items[0]["document_id"]
    async with sessionmaker() as s:
        h = await s.scalar(text("SELECT content_hash FROM app.documents WHERE id = :d"), {"d": doc})
    assert await qdrant_index.count(h) > 0
    # ごみ箱に無いものは完全削除できない
    assert (await client.delete(f"/v1/documents/{doc}/purge", headers=ALICE)).status_code == 404
    await client.delete(f"/v1/documents/{doc}", headers=ALICE)
    # 24 時間を過ぎた本人は 403
    async with sessionmaker() as s:
        await s.execute(text("UPDATE app.documents SET deleted_at = now() - interval '25 hours'"))
        await s.commit()
    trash = (await client.get("/v1/trash", headers=ALICE)).json()
    assert (
        trash[0]["kind"] == "document" and trash[0]["purgeable"] is False and trash[0]["remaining_days"] == 28
    )
    assert (await client.delete(f"/v1/documents/{doc}/purge", headers=ALICE)).status_code == 403
    async with sessionmaker() as s:
        await s.execute(text("UPDATE app.documents SET deleted_at = now()"))
        await s.commit()
    assert (await client.delete(f"/v1/documents/{doc}/purge", headers=ALICE)).status_code == 204
    # 参照 0 → 点・行も消える
    assert await qdrant_index.count(h) == 0
    async with sessionmaker() as s:
        assert await s.scalar(text("SELECT count(*) FROM app.contents")) == 0
        assert await s.scalar(text("SELECT action FROM app.audit_logs WHERE action='document.purge'"))


async def test_purge_keeps_shared_content(
    make_client: Callable[..., Awaitable[httpx.AsyncClient]],
    sessionmaker: async_sessionmaker[AsyncSession],
    qdrant_index: QdrantIndex,
    storage_root: str,
) -> None:
    client = await make_client(index=qdrant_index)
    _, items = await _ingested(client, sessionmaker, qdrant_index, storage_root, [("a.md", MD.encode())])
    org = (await client.post("/v1/kbs", json={"name": "全社"}, headers=ADMIN)).json()["id"]
    other = (await _upload(client, org, [("a.md", MD.encode())], headers=ADMIN)).json()["items"][0]
    await client.delete(f"/v1/documents/{other['document_id']}", headers=ADMIN)
    assert (
        await client.delete(f"/v1/documents/{other['document_id']}/purge", headers=ADMIN)
    ).status_code == 204
    async with sessionmaker() as s:
        assert await s.scalar(text("SELECT ref_count FROM app.contents")) == 1
    # 残った文書の参照は引き続き使える
    assert (
        await client.get(f"/v1/documents/{items[0]['document_id']}/outline", headers=ALICE)
    ).status_code == 200


async def test_previews(
    make_client: Callable[..., Awaitable[httpx.AsyncClient]],
    sessionmaker: async_sessionmaker[AsyncSession],
    qdrant_index: QdrantIndex,
    storage_root: str,
) -> None:
    client = await make_client(index=qdrant_index)
    _, items = await _ingested(client, sessionmaker, qdrant_index, storage_root, [("規程.md", MD.encode())])
    doc = items[0]["document_id"]
    res = await client.get(f"/v1/documents/{doc}/original", headers=ALICE)
    assert res.status_code == 200 and res.content == MD.encode()
    assert res.headers["accept-ranges"] == "bytes"
    res = await client.get(f"/v1/documents/{doc}/original", headers={**ALICE, "Range": "bytes=2-5"})
    assert res.status_code == 206 and res.content == MD.encode()[2:6]
    assert res.headers["content-range"] == f"bytes 2-5/{len(MD.encode())}"
    res = await client.get(f"/v1/documents/{doc}/original", headers={**ALICE, "Range": "bytes=-3"})
    assert res.content == MD.encode()[-3:]
    res = await client.get(f"/v1/documents/{doc}/original", headers={**ALICE, "Range": "bytes=9999-"})
    assert res.status_code == 416
    assert (await client.get(f"/v1/documents/{doc}/rendered", headers=ALICE)).text == MD

    outline = (await client.get(f"/v1/documents/{doc}/outline", headers=ALICE)).json()
    assert [s["heading_path"] for s in outline] == ["総則 > 目的", "総則 > 定義"]
    assert all(s["chunk_count"] >= 1 for s in outline)
    sec = (await client.get(f"/v1/documents/{doc}/sections/{outline[1]['id']}", headers=ALICE)).json()
    assert "MX-17" in sec["text"]
    chunks = (await client.get(f"/v1/documents/{doc}/chunks", headers=ALICE)).json()
    assert chunks[0]["context"].startswith("規程 >") and chunks[0]["section_id"] == outline[0]["id"]
    for bad in ["..%2Fdocling.json", ".hidden", "x"]:
        assert (await client.get(f"/v1/documents/{doc}/assets/{bad}", headers=ALICE)).status_code == 404
    # 他人は参照できない
    assert (await client.get(f"/v1/documents/{doc}/original", headers=BOB)).status_code == 404


async def test_trash_lists_only_restorable(client: httpx.AsyncClient) -> None:
    kb = await _personal(client, ALICE)
    items = (
        await _upload(client, kb, [("a.txt", b"a"), ("b.txt", b"b")], paths=["F/G/a.txt", "b.txt"])
    ).json()["items"]
    folders = {f["name"]: f["id"] for f in (await client.get(f"/v1/kbs/{kb}/folders", headers=ALICE)).json()}
    await client.delete(f"/v1/folders/{folders['F']}", headers=ALICE)
    await client.delete(f"/v1/documents/{items[1]['document_id']}", headers=ALICE)
    org = (await client.post("/v1/kbs", json={"name": "全社"}, headers=ADMIN)).json()["id"]
    await client.delete(f"/v1/kbs/{org}", headers=ADMIN)

    trash = (await client.get("/v1/trash", headers=ALICE)).json()
    # F の配下（G・a.txt）は F にまとめる。全社 KB は member のごみ箱に出ない
    assert sorted((t["kind"], t["name"]) for t in trash) == [("document", "b.txt"), ("folder", "F")]
    assert trash[0]["remaining_days"] in (29, 30)
    admin_trash = (await client.get("/v1/trash", headers=ADMIN)).json()
    assert [(t["kind"], t["name"]) for t in admin_trash] == [("kb", "全社")]
    assert (await client.get("/v1/trash", headers=as_user("carol"))).json() == []
