"""部門と共有 KB の共有リスト（specs/024）。"""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .conftest import ADMIN, ALICE, BOB, as_user
from .test_ingest import _upload

pytestmark = pytest.mark.integration

CAROL = as_user("carol")
ADMIN2 = as_user("admin2", "admin")


async def _dept(client: httpx.AsyncClient, name: str, members: dict[str, str]) -> str:
    d = (await client.post("/v1/departments", json={"name": name}, headers=ADMIN)).json()["id"]
    for uid, role in members.items():
        res = await client.put(f"/v1/departments/{d}/members/{uid}", json={"role": role}, headers=ADMIN)
        assert res.status_code == 200, res.text
    return str(d)


async def _kb(client: httpx.AsyncClient, name: str, headers: dict[str, str] = ADMIN, **body: str) -> str:
    res = await client.post("/v1/kbs", json={"name": name, **body}, headers=headers)
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


def _ids(res: httpx.Response) -> set[str]:
    return {k["id"] for k in res.json() if k["kind"] == "org"}


async def test_admin_created_kb_is_open_to_everyone_and_managed_by_creator(client: httpx.AsyncClient) -> None:
    kb = await _kb(client, "就業規則")
    shares = (await client.get(f"/v1/kbs/{kb}/shares", headers=ALICE)).json()
    assert shares["shares"] == [
        {"subject_type": "everyone", "subject_id": "", "role": "viewer"},
        {"subject_type": "user", "subject_id": "admin1", "role": "manager"},
    ]
    assert shares["can_manage"] is False
    alice = next(k for k in (await client.get("/v1/kbs", headers=ALICE)).json() if k["id"] == kb)
    assert alice["role"] == "viewer" and alice["writable"] is False and alice["shared_with_everyone"] is True
    # 作った admin は管理、別の admin は役割が無くても管理はできる
    mine = next(k for k in (await client.get("/v1/kbs", headers=ADMIN)).json() if k["id"] == kb)
    assert mine["role"] == "manager" and mine["can_manage"] is True


async def test_department_share_limits_readers(client: httpx.AsyncClient) -> None:
    hr = await _dept(client, "人事部", {"alice": "member"})
    kb = await _kb(client, "人事資料")
    res = await client.put(
        f"/v1/kbs/{kb}/shares",
        json={
            "shares": [
                {"subject_type": "department", "subject_id": hr, "role": "viewer"},
                {"subject_type": "user", "subject_id": "carol", "role": "editor"},
                {"subject_type": "user", "subject_id": "admin1", "role": "manager"},
            ]
        },
        headers=ADMIN,
    )
    assert res.status_code == 200, res.text
    assert kb in _ids(await client.get("/v1/kbs", headers=ALICE))
    assert kb not in _ids(await client.get("/v1/kbs", headers=BOB))
    assert (await client.get(f"/v1/documents?kb_id={kb}", headers=BOB)).status_code == 404
    assert (await client.get(f"/v1/kbs/{kb}/shares", headers=BOB)).status_code == 404
    # 編集の人は文書を足せる。閲覧だけの人は 403
    assert (await _upload(client, kb, [("a.txt", b"a")], CAROL)).status_code == 200
    assert (await _upload(client, kb, [("b.txt", b"b")], ALICE)).status_code == 403
    # 部門の行には部門の人を添える
    shares = (await client.get(f"/v1/kbs/{kb}/shares", headers=ALICE)).json()
    assert shares["department_members"] == {hr: ["alice"]}
    # 部門から外すと、すぐ見えなくなる
    assert (await client.delete(f"/v1/departments/{hr}/members/alice", headers=ADMIN)).status_code == 204
    assert kb not in _ids(await client.get("/v1/kbs", headers=ALICE))


async def test_admin_without_share_cannot_read_but_can_manage(client: httpx.AsyncClient) -> None:
    kb = await _kb(client, "経営会議")
    await client.put(
        f"/v1/kbs/{kb}/shares",
        json={"shares": [{"subject_type": "user", "subject_id": "admin1", "role": "manager"}]},
        headers=ADMIN,
    )
    assert kb not in _ids(await client.get("/v1/kbs", headers=ADMIN2))
    assert (await client.get(f"/v1/documents?kb_id={kb}", headers=ADMIN2)).status_code == 404
    # 管理のための一覧には出る（中身は読めない）
    listed = next(
        k for k in (await client.get("/v1/kbs?manageable=true", headers=ADMIN2)).json() if k["id"] == kb
    )
    assert listed["role"] is None and listed["can_manage"] is True and listed["document_count"] == 0
    assert (await client.get(f"/v1/kbs/{kb}/shares", headers=ADMIN2)).status_code == 200
    # 自分を足せば読める（監査に残る）
    res = await client.put(
        f"/v1/kbs/{kb}/shares",
        json={
            "shares": [
                {"subject_type": "user", "subject_id": "admin1", "role": "manager"},
                {"subject_type": "user", "subject_id": "admin2", "role": "viewer"},
            ]
        },
        headers=ADMIN2,
    )
    assert res.status_code == 200
    assert kb in _ids(await client.get("/v1/kbs", headers=ADMIN2))
    audit = (await client.get("/v1/admin/audit?action=kb.share_add", headers=ADMIN)).json()["items"]
    assert any(e["resource_id"] == kb and e["detail"]["subject_id"] == "admin2" for e in audit)


async def test_share_list_rules(client: httpx.AsyncClient) -> None:
    kb = await _kb(client, "規則")
    put = lambda shares: client.put(f"/v1/kbs/{kb}/shares", json={"shares": shares}, headers=ADMIN)  # noqa: E731
    # 全員には閲覧だけ
    res = await put(
        [
            {"subject_type": "everyone", "role": "editor"},
            {"subject_type": "user", "subject_id": "admin1", "role": "manager"},
        ]
    )
    assert res.status_code == 400
    # 管理が 1 行も無いのは不可
    assert (await put([{"subject_type": "everyone", "role": "viewer"}])).status_code == 400
    # 無い部門は不可
    res = await put(
        [
            {
                "subject_type": "department",
                "subject_id": "00000000-0000-0000-0000-000000000000",
                "role": "viewer",
            },
            {"subject_type": "user", "subject_id": "admin1", "role": "manager"},
        ]
    )
    assert res.status_code == 400
    # 編集者は共有リストを変えられない
    await put(
        [
            {"subject_type": "user", "subject_id": "alice", "role": "editor"},
            {"subject_type": "user", "subject_id": "admin1", "role": "manager"},
        ]
    )
    res = await client.put(f"/v1/kbs/{kb}/shares", json={"shares": []}, headers=ALICE)
    assert res.status_code == 403
    # 個人 KB には共有リストが無い
    personal = next(k for k in (await client.get("/v1/kbs", headers=ALICE)).json() if k["kind"] == "personal")
    assert (await client.get(f"/v1/kbs/{personal['id']}/shares", headers=ALICE)).status_code == 404


async def test_department_manager_creates_kb_for_own_department(client: httpx.AsyncClient) -> None:
    mfg = await _dept(client, "製造部", {"alice": "manager", "bob": "member"})
    other = await _dept(client, "営業部", {"carol": "member"})
    assert (await client.post("/v1/kbs", json={"name": "x"}, headers=BOB)).status_code == 403
    res = await client.post("/v1/kbs", json={"name": "x", "department_id": other}, headers=ALICE)
    assert res.status_code == 403
    kb = await _kb(client, "設備マニュアル", ALICE, department_id=mfg)
    shares = (await client.get(f"/v1/kbs/{kb}/shares", headers=BOB)).json()["shares"]
    assert shares == [
        {"subject_type": "department", "subject_id": mfg, "role": "viewer"},
        {"subject_type": "user", "subject_id": "alice", "role": "manager"},
    ]
    assert kb not in _ids(await client.get("/v1/kbs", headers=CAROL))
    # 部門管理者はメンバーを足せるが、部門管理者は指名できない
    assert (
        await client.put(f"/v1/departments/{mfg}/members/carol", json={"role": "member"}, headers=ALICE)
    ).status_code == 200
    res = await client.put(f"/v1/departments/{mfg}/members/carol", json={"role": "manager"}, headers=ALICE)
    assert res.status_code == 403
    # 他の部門は触れない
    res = await client.put(f"/v1/departments/{other}/members/bob", json={"role": "member"}, headers=ALICE)
    assert res.status_code == 403


async def test_departments_crud_and_listing(client: httpx.AsyncClient) -> None:
    d = await _dept(client, "品質保証部", {"alice": "manager", "bob": "member"})
    listed = (await client.get("/v1/departments", headers=BOB)).json()
    row = next(x for x in listed if x["id"] == d)
    assert row["name"] == "品質保証部" and row["member_count"] == 2 and row["my_role"] == "member"
    members = (await client.get(f"/v1/departments/{d}/members", headers=BOB)).json()
    assert members == [{"user_id": "alice", "role": "manager"}, {"user_id": "bob", "role": "member"}]
    assert (await client.post("/v1/departments", json={"name": "x"}, headers=ALICE)).status_code == 403
    dup = await client.post("/v1/departments", json={"name": "品質保証部"}, headers=ADMIN)
    assert dup.status_code == 409
    assert (await client.patch(f"/v1/departments/{d}", json={"name": "品証部"}, headers=ADMIN)).json()[
        "name"
    ] == "品証部"
    # 消すと、その部門を指す共有リストの行も消える
    kb = await _kb(client, "品質")
    await client.put(
        f"/v1/kbs/{kb}/shares",
        json={
            "shares": [
                {"subject_type": "department", "subject_id": d, "role": "viewer"},
                {"subject_type": "user", "subject_id": "admin1", "role": "manager"},
            ]
        },
        headers=ADMIN,
    )
    assert (await client.delete(f"/v1/departments/{d}", headers=ADMIN)).status_code == 204
    shares = (await client.get(f"/v1/kbs/{kb}/shares", headers=ADMIN)).json()["shares"]
    assert shares == [{"subject_type": "user", "subject_id": "admin1", "role": "manager"}]


async def test_user_access_reasons(client: httpx.AsyncClient) -> None:
    mfg = await _dept(client, "製造部2", {"alice": "member"})
    open_kb = await _kb(client, "全社向け")
    dept_kb = await _kb(client, "製造向け")
    await client.put(
        f"/v1/kbs/{dept_kb}/shares",
        json={
            "shares": [
                {"subject_type": "department", "subject_id": mfg, "role": "viewer"},
                {"subject_type": "user", "subject_id": "alice", "role": "editor"},
                {"subject_type": "user", "subject_id": "admin1", "role": "manager"},
            ]
        },
        headers=ADMIN,
    )
    assert (await client.get("/v1/admin/users/alice/access", headers=ALICE)).status_code == 403
    rows = {r["kb_id"]: r for r in (await client.get("/v1/admin/users/alice/access", headers=ADMIN)).json()}
    assert rows[open_kb]["role"] == "viewer"
    assert rows[open_kb]["reasons"] == [{"subject_type": "everyone", "subject_id": "", "role": "viewer"}]
    assert rows[dept_kb]["role"] == "editor"
    assert {(r["subject_type"], r["role"]) for r in rows[dept_kb]["reasons"]} == {
        ("department", "viewer"),
        ("user", "editor"),
    }


async def test_shared_thread_hides_sources_viewer_cannot_read(
    client: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    """R16: 共有スレッドの引用は、見る人が読めない文書なら文書名を伏せる。"""
    from arag.db.models import Message, Thread

    secret = await _kb(client, "役員会")
    await client.put(
        f"/v1/kbs/{secret}/shares",
        json={"shares": [{"subject_type": "user", "subject_id": "admin1", "role": "manager"}]},
        headers=ADMIN,
    )
    public = await _kb(client, "社内規程")
    s_doc = (await _upload(client, secret, [("役員報酬.txt", b"x")], ADMIN)).json()["items"][0]["document_id"]
    p_doc = (await _upload(client, public, [("就業規則.txt", b"y")], ADMIN)).json()["items"][0]["document_id"]
    async with sessionmaker() as s:
        t = Thread(user_id="admin1", title="t", visibility="org", share_token="tok024")
        s.add(t)
        await s.flush()
        s.add(
            Message(
                thread_id=t.id,
                ordinal=0,
                query="q",
                answer_text="a [1][2]",
                citation_map={
                    "1": {"source_id": s_doc, "section_id": "x"},
                    "2": {"source_id": p_doc, "section_id": "y"},
                },
                sources=[
                    {"id": s_doc, "title": "役員報酬.txt", "sections": []},
                    {"id": p_doc, "title": "就業規則.txt", "sections": []},
                ],
            )
        )
        await s.commit()
    seen = (await client.get("/v1/shared/tok024", headers=BOB)).json()["messages"][0]["sources"]
    assert [(x["title"], x["restricted"]) for x in seen] == [
        ("閲覧できない資料", True),
        ("就業規則.txt", False),
    ]
    mine = (await client.get("/v1/shared/tok024", headers=ADMIN)).json()["messages"][0]["sources"]
    assert [x["title"] for x in mine] == ["役員報酬.txt", "就業規則.txt"]


async def test_search_scope_follows_shares(
    client: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    """エージェントの検索範囲も共有リストに従う（R15）。"""
    from arag.auth.principal import Principal
    from arag.search.schemas import SearchRequest
    from arag.search.scope import resolve_scope

    kb = await _kb(client, "限定")
    await client.put(
        f"/v1/kbs/{kb}/shares",
        json={"shares": [{"subject_type": "user", "subject_id": "alice", "role": "manager"}]},
        headers=ADMIN,
    )
    req = SearchRequest(query="x")
    async with sessionmaker() as s:
        alice = await resolve_scope(s, Principal(user_id="alice"), req)
        admin = await resolve_scope(s, Principal(user_id="admin2", role="admin"), req)
    assert kb in alice.kb_ids and kb not in admin.kb_ids
