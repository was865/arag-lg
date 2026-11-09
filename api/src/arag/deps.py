"""ルーターが使う共通の依存関数。"""

import hmac
import ipaddress
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from arag.audit import AuditEvent, write_audit
from arag.auth.principal import CurrentPrincipal, Principal
from arag.ingest.events import Publisher
from arag.kb.access import Access, load_access
from arag.kb.sync import PayloadSync
from arag.settings import Settings
from arag.storage import Storage


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_storage(request: Request) -> Storage:
    storage: Storage = request.app.state.storage
    return storage


def request_id_of(request: Request) -> str | None:
    # RequestIdMiddleware が scope["state"] に入れた値（受信ヘッダが不正なら採番済み）
    rid: str | None = getattr(request.state, "request_id", None)
    return rid


def client_ip(request: Request, forward_secret: str) -> str | None:
    """監査ログに残す IP。Web の中継が合言葉付きで伝えた利用者の IP を優先する。

    合言葉が無い・合わない・形が IP でないときは、接続元（ふつうは Web のコンテナ）を使う。
    """
    peer = request.client.host if request.client else None
    if not forward_secret:
        return peer
    token = request.headers.get("x-arag-forward-token", "")
    claimed = request.headers.get("x-arag-client-ip", "").strip()
    if not claimed or not hmac.compare_digest(token.encode(), forward_secret.encode()):
        return peer
    try:
        return str(ipaddress.ip_address(claimed))
    except ValueError:
        return peer


@dataclass(frozen=True, slots=True)
class Ctx:
    """ルーターで毎回使う組（利用者・DB・監査用の要求情報）。"""

    principal: Principal
    session: AsyncSession
    # 共有 KB の役割（specs/024）。要求ごとに 1 回だけ読む
    access: Access
    request_id: str | None
    ip: str | None
    payload_sync: PayloadSync
    publisher: Publisher

    async def audit(self, event: AuditEvent) -> None:
        await write_audit(
            self.session, event, principal=self.principal, request_id=self.request_id, ip=self.ip
        )


async def get_ctx(
    request: Request,
    principal: CurrentPrincipal,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Ctx:
    return Ctx(
        principal=principal,
        session=session,
        access=await load_access(session, principal),
        request_id=request_id_of(request),
        ip=client_ip(request, get_settings(request).forward_secret.get_secret_value()),
        payload_sync=request.app.state.payload_sync,
        publisher=request.app.state.publisher,
    )


CtxDep = Annotated[Ctx, Depends(get_ctx)]
