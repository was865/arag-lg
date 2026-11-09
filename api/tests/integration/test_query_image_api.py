"""質問に添える画像の API（specs/017-query-image A2・A3・A5）。runner は動かさない。"""

import base64
import io
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.agent.query_image import DEFAULT_QUERY
from arag.db.models import Message, Run
from arag.settings import Settings

from .conftest import ALICE, BOB
from .test_agent_api import MODELS

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    r = Redis.from_url(Settings().redis_url, decode_responses=True)
    try:
        await r.ping()
    except Exception as e:
        pytest.skip(f"redis に接続できません: {e}")
    yield r
    await r.aclose()


async def _ask(c: httpx.AsyncClient, url: str = "/v1/runs", q: str = "これは?") -> dict[str, Any]:
    r = await c.post(url, json={"query": q, "image": {"data": _png()}}, headers=ALICE)
    assert r.status_code == 202, r.text
    body: dict[str, Any] = r.json()
    return body


def _png(size: tuple[int, int] = (64, 48)) -> str:
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 120, 200)).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
async def api(make_client: Callable[..., Awaitable[httpx.AsyncClient]], redis: Redis) -> httpx.AsyncClient:
    return await make_client(
        chat_models=MODELS,
        rate_limit_runs_per_min=0,
        vlm_model="openai:qwen3-vl",
        vlm_base_url="http://vlm/v1",
        query_image_max_px=32,
    )


async def _finish(sm: async_sessionmaker[AsyncSession], run_id: str, description: str = "銘板 MX-17") -> str:
    """runner の代わりに完了させる（request は runner と同じく保存し、読み取り結果も入れる）。"""
    async with sm() as s:
        run = await s.get(Run, uuid.UUID(run_id))
        assert run is not None
        run.status = "completed"
        req: dict[str, Any] = {k: v for k, v in run.request.items() if k != "principal"}
        if req.get("image"):
            req["image"] = {**req["image"], "description": description}
        s.add(
            Message(
                id=run.message_id,
                thread_id=run.thread_id,
                ordinal=int(req["ordinal"]),
                query=req["query"],
                answer_text="回答",
                model_id=run.model_id,
                steps=[],
                sources=[],
                citation_map={},
                request=req,
                run_id=run.id,
            )
        )
        await s.commit()
        return str(run.message_id)


async def test_image_rejected_when_vlm_unset(
    make_client: Callable[..., Awaitable[httpx.AsyncClient]],
    redis: Redis,
) -> None:
    c = await make_client(chat_models=MODELS, rate_limit_runs_per_min=0, vlm_model="")
    r = await c.get("/v1/models", headers=ALICE)
    assert r.json()["image_input"] is False
    r = await c.post("/v1/runs", json={"query": "これは何", "image": {"data": _png()}}, headers=ALICE)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "image_unsupported"


async def test_run_stores_shrunk_jpeg(api: httpx.AsyncClient, sessionmaker: Any, storage_root: str) -> None:
    assert (await api.get("/v1/models", headers=ALICE)).json()["image_input"] is True
    r = await api.post("/v1/runs", json={"query": "この部品は?", "image": {"data": _png()}}, headers=ALICE)
    assert r.status_code == 202, r.text
    async with sessionmaker() as s:
        run = await s.get(Run, uuid.UUID(r.json()["run_id"]))
        img = run.request["image"]
    assert (img["width"], img["height"]) == (32, 24)
    assert img["key"] == f"queries/alice/{img['id']}.jpg"
    assert (Path(storage_root) / img["key"]).read_bytes()[:3] == b"\xff\xd8\xff"


async def test_image_only_uses_default_query(api: httpx.AsyncClient, sessionmaker: Any) -> None:
    r = await api.post("/v1/runs", json={"query": "  ", "image": {"data": _png()}}, headers=ALICE)
    assert r.status_code == 202, r.text
    async with sessionmaker() as s:
        run = await s.get(Run, uuid.UUID(r.json()["run_id"]))
        assert run.request["query"] == DEFAULT_QUERY
    # 画像も文字も無ければ従来どおり断る
    r = await api.post("/v1/runs", json={"query": " "}, headers=ALICE)
    assert r.status_code == 422


async def test_invalid_image(api: httpx.AsyncClient) -> None:
    bad = base64.b64encode(b"not an image").decode()
    r = await api.post("/v1/runs", json={"query": "x", "image": {"data": bad}}, headers=ALICE)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_image"


async def test_message_image_visible_to_owner_only(api: httpx.AsyncClient, sessionmaker: Any) -> None:
    r = await api.post("/v1/runs", json={"query": "これは?", "image": {"data": _png()}}, headers=ALICE)
    body = r.json()
    mid = await _finish(sessionmaker, body["run_id"])
    tid = body["thread_id"]
    detail = (await api.get(f"/v1/threads/{tid}", headers=ALICE)).json()
    assert detail["messages"][0]["image"] == {"width": 32, "height": 24, "description": "銘板 MX-17"}
    url = f"/v1/threads/{tid}/messages/{mid}/image"
    got = await api.get(url, headers=ALICE)
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
    assert got.content[:3] == b"\xff\xd8\xff"
    assert (await api.get(url, headers=BOB)).status_code == 404


async def test_message_without_image(api: httpx.AsyncClient, sessionmaker: Any) -> None:
    body = (await api.post("/v1/runs", json={"query": "文字だけ"}, headers=ALICE)).json()
    mid = await _finish(sessionmaker, body["run_id"])
    detail = (await api.get(f"/v1/threads/{body['thread_id']}", headers=ALICE)).json()
    assert detail["messages"][0]["image"] is None
    r = await api.get(f"/v1/threads/{body['thread_id']}/messages/{mid}/image", headers=ALICE)
    assert r.status_code == 404


async def test_shared_page_marks_image_without_serving_it(api: httpx.AsyncClient, sessionmaker: Any) -> None:
    body = await _ask(api)
    await _finish(sessionmaker, body["run_id"])
    tid = body["thread_id"]
    token = (await api.patch(f"/v1/threads/{tid}", json={"visibility": "org"}, headers=ALICE)).json()[
        "share_token"
    ]
    shared = (await api.get(f"/v1/shared/{token}", headers=BOB)).json()
    assert shared["messages"][0]["has_image"] is True
    assert "image" not in shared["messages"][0]


async def test_delete_thread_removes_images(
    api: httpx.AsyncClient, sessionmaker: Any, storage_root: str
) -> None:
    body = await _ask(api)
    await _finish(sessionmaker, body["run_id"])
    # 2 つ目は実行中のまま（run だけにある画像も消す）
    await _ask(api, f"/v1/threads/{body['thread_id']}/runs", "続き")
    files = list((Path(storage_root) / "queries" / "alice").glob("*.jpg"))
    assert files
    assert (await api.delete(f"/v1/threads/{body['thread_id']}", headers=ALICE)).status_code == 204
    assert not any(f.exists() for f in files)
