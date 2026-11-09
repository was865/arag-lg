"""利用状況の分析（specs/012-analytics A1、R1〜R6）。"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.db.models import Citation, Message, MessageFeedback, Thread

from .conftest import ADMIN, ALICE

pytestmark = pytest.mark.integration


@pytest.fixture
async def api(make_client: Callable[..., Awaitable[httpx.AsyncClient]]) -> httpx.AsyncClient:
    return await make_client()


async def _seed(sm: async_sessionmaker[AsyncSession]) -> None:
    now = datetime.now(UTC)
    async with sm() as s:
        ta = Thread(id=uuid.uuid4(), user_id="alice", title="a")
        tb = Thread(id=uuid.uuid4(), user_id="bob", title="b")
        s.add_all([ta, tb])
        await s.flush()
        rows = [
            # (thread, 何日前, 理由, 状態, 時間 ms)
            (ta, 0, None, "completed", 1000),
            (ta, 0, "no_relevant_sources", "completed", 3000),
            (tb, 2, None, "completed", 2000),
            (tb, 2, None, "cancelled", 500),
            (tb, 40, None, "completed", 9000),  # 30 日の外
        ]
        msgs = []
        for i, (t, ago, reason, status, ms) in enumerate(rows):
            m = Message(
                id=uuid.uuid4(),
                thread_id=t.id,
                ordinal=i + 1,
                query=f"質問{i}",
                answer_text="",
                status=status,
                no_answer_reason=reason,
                duration_ms=ms,
                tokens_in=100,
                tokens_out=10,
                created_at=now - timedelta(days=ago),
            )
            msgs.append(m)
        s.add_all(msgs)
        await s.flush()
        s.add_all(
            [
                Citation(
                    message_id=msgs[0].id, ordinal=1, document_id=uuid.uuid4(), document_title="台帳.pdf"
                ),
                Citation(message_id=msgs[0].id, ordinal=2, document_title="台帳.pdf"),
                Citation(message_id=msgs[2].id, ordinal=1, document_title="台帳.pdf"),
                Citation(message_id=msgs[2].id, ordinal=2, document_title="手順.md"),
                Citation(message_id=msgs[4].id, ordinal=1, document_title="古い.pdf"),
            ]
        )
        s.add_all(
            [
                MessageFeedback(message_id=msgs[0].id, user_id="alice", rating="up", reason_tags=[]),
                MessageFeedback(
                    message_id=msgs[1].id, user_id="alice", rating="down", reason_tags=["根拠が違う", "古い"]
                ),
                MessageFeedback(
                    message_id=msgs[2].id, user_id="bob", rating="down", reason_tags=["根拠が違う"]
                ),
            ]
        )
        await s.commit()


async def test_only_admins(api: httpx.AsyncClient) -> None:
    assert (await api.get("/v1/admin/analytics", headers=ALICE)).status_code == 403
    assert (await api.get("/v1/admin/analytics", params={"days": 5}, headers=ADMIN)).status_code == 422


async def test_summary(api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    await _seed(sessionmaker)
    b = (await api.get("/v1/admin/analytics", params={"days": 30}, headers=ADMIN)).json()
    t = b["totals"]
    assert t["questions"] == 4 and t["users"] == 2
    # 完了 3 件のうち答えられたのは 2 件
    assert t["answered_rate"] == pytest.approx(2 / 3)
    assert t["median_duration_ms"] == 1500  # 取り消しを含む 4 件の中央値（500, 1000, 2000, 3000）
    assert t["tokens_in"] == 400 and t["tokens_out"] == 40

    assert len(b["daily"]) == 30
    today = b["daily"][-1]
    assert today["questions"] == 2 and today["no_answer"] == 1
    assert b["daily"][-3]["questions"] == 2 and b["daily"][-2]["questions"] == 0

    assert b["no_answer_reasons"] == [{"reason": "no_relevant_sources", "count": 1}]
    [gap] = b["recent_gaps"]
    assert gap["query"] == "質問1" and gap["reason"] == "no_relevant_sources"

    assert b["feedback"]["up"] == 1 and b["feedback"]["down"] == 2
    assert b["feedback"]["top_down_tags"][0] == {"tag": "根拠が違う", "count": 2}

    assert b["top_documents"][0] == {"title": "台帳.pdf", "citations": 3, "answers": 2}
    assert [d["title"] for d in b["top_documents"]] == ["台帳.pdf", "手順.md"]
