"""技術者への報告（specs/028 R11〜R17、T10・T11）。"""

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.db.models import AuditLog

from .conftest import ADMIN, ALICE, BOB
from .test_agent_api import _ask, _finish
from .test_agent_api import api as api  # fixture をこのモジュールでも使う
from .test_agent_api import redis as redis

pytestmark = pytest.mark.integration


async def _report(
    api: httpx.AsyncClient, sm: async_sessionmaker[AsyncSession], q: str, rating: str, tags: list[str]
) -> str:
    created = await _ask(api, q)
    mid = await _finish(sm, created["run_id"], 1, answer=f"{q}の回答 [1]")
    r = await api.put(
        f"/v1/messages/{mid}/feedback",
        json={"rating": rating, "reason_tags": tags, "comment": "数字が違う" + "。" * 100 if tags else None},
        headers=ALICE,
    )
    assert r.status_code == 200, r.text
    return mid


async def test_reason_tags_are_checked_and_error_is_allowed(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    created = await _ask(api, "質問")
    mid = await _finish(sessionmaker, created["run_id"], 1)
    url = f"/v1/messages/{mid}/feedback"
    ok = await api.put(url, json={"rating": "down", "reason_tags": ["error", "wrong"]}, headers=ALICE)
    assert ok.status_code == 200
    bad = await api.put(url, json={"rating": "down", "reason_tags": ["根拠が違う"]}, headers=ALICE)
    assert bad.status_code == 422


async def test_only_admins_can_read_reports(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _report(api, sessionmaker, "在庫は？", "down", ["wrong"])
    page = (await api.get("/v1/admin/feedback", headers=ADMIN)).json()
    fid = page["items"][0]["id"]
    for h in (ALICE, BOB):
        assert (await api.get("/v1/admin/feedback", headers=h)).status_code == 403
        assert (await api.get(f"/v1/admin/feedback/{fid}", headers=h)).status_code == 403
        assert (await api.post(f"/v1/admin/feedback/{fid}/resolve", headers=h)).status_code == 403


async def test_list_filters_and_shortens(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await _report(api, sessionmaker, "在庫は？" + "あ" * 100, "down", ["wrong"])
    await _report(api, sessionmaker, "単価は？", "up", [])
    page = (await api.get("/v1/admin/feedback", headers=ADMIN)).json()
    assert [x["rating"] for x in page["items"]] == ["up", "down"]  # 新しい順
    down = page["items"][1]
    assert down["status"] == "open" and down["reason_tags"] == ["wrong"] and down["user_id"] == "alice"
    assert len(down["query"]) <= 80 and len(down["comment"]) <= 80
    assert down["model_id"] and "no_answer_reason" in down
    assert page["open_count"] == 1  # 未対応の「良くない」の件数（ナビに出す）
    only = (
        await api.get("/v1/admin/feedback", params={"rating": "down", "status": "open"}, headers=ADMIN)
    ).json()
    assert [x["id"] for x in only["items"]] == [down["id"]]
    p1 = (await api.get("/v1/admin/feedback", params={"limit": 1}, headers=ADMIN)).json()
    p2 = (
        await api.get("/v1/admin/feedback", params={"limit": 1, "cursor": p1["next_cursor"]}, headers=ADMIN)
    ).json()
    assert p1["items"][0]["id"] != p2["items"][0]["id"] and p2["next_cursor"] is None


async def test_detail_has_the_whole_turn(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    mid = await _report(api, sessionmaker, "在庫は？", "down", ["wrong"])
    fid = (await api.get("/v1/admin/feedback", headers=ADMIN)).json()["items"][0]["id"]
    d = (await api.get(f"/v1/admin/feedback/{fid}", headers=ADMIN)).json()
    assert d["comment"].startswith("数字が違う") and len(d["comment"]) > 80
    m = d["message"]
    assert m["id"] == mid and m["query"] == "在庫は？" and m["answer"] == "在庫は？の回答 [1]"
    assert m["steps"][0]["label"] == "検索" and m["citation_map"]["1"]["section_id"] == "x1"
    assert d["thread_title"] and "duration_ms" in m and "tokens_in" in m
    assert (await api.get(f"/v1/admin/feedback/{mid}", headers=ADMIN)).status_code == 404


async def test_resolve_and_reopen_are_audited(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    mid = await _report(api, sessionmaker, "在庫は？", "down", ["wrong"])
    fid = (await api.get("/v1/admin/feedback", headers=ADMIN)).json()["items"][0]["id"]
    r = await api.post(f"/v1/admin/feedback/{fid}/resolve", headers=ADMIN)
    assert r.status_code == 200 and r.json()["status"] == "resolved" and r.json()["resolved_by"] == "admin1"
    assert (await api.get("/v1/admin/feedback", headers=ADMIN)).json()["open_count"] == 0
    r = await api.post(f"/v1/admin/feedback/{fid}/reopen", headers=ADMIN)
    assert r.json()["status"] == "open" and r.json()["resolved_by"] is None
    async with sessionmaker() as s:
        acts = [a.action for a in await s.scalars(select(AuditLog).where(AuditLog.resource_id == fid))]
    assert sorted(acts) == ["feedback.reopen", "feedback.resolve"]
    # 利用者が報告を直したら、未対応に戻す
    await api.post(f"/v1/admin/feedback/{fid}/resolve", headers=ADMIN)
    await api.put(
        f"/v1/messages/{mid}/feedback", json={"rating": "down", "reason_tags": ["error"]}, headers=ALICE
    )
    assert (await api.get(f"/v1/admin/feedback/{fid}", headers=ADMIN)).json()["status"] == "open"
