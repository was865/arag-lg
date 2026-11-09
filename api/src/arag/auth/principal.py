"""利用者（Principal）の解決（specs/003-ingestion R1・R2）。

- jwt（本番）: Next が付ける `Authorization: Bearer <JWT>` を Better Auth の JWKS で検証する
  （specs/006-auth）。
- dev: 開発・評価用。X-Dev-User-Id / X-Dev-Role ヘッダで利用者を指定する。
"""

from dataclasses import dataclass
from typing import Annotated, Literal, cast

from fastapi import Depends, Request

from arag.errors import ApiError
from arag.settings import Settings

Role = Literal["owner", "admin", "member"]
ROLES: frozenset[str] = frozenset({"owner", "admin", "member"})


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    role: Role = "member"
    email: str | None = None
    email_verified: bool = True

    @property
    def is_admin(self) -> bool:
        return self.role in ("owner", "admin")


def unauthenticated() -> ApiError:
    return ApiError(401, "unauthenticated", "ログインが必要です")


def principal_from_dev_headers(
    user_id: str | None, role: str | None, verified: str | None = None
) -> Principal:
    if not user_id or len(user_id) > 64:
        raise unauthenticated()
    role = role or "member"
    if role not in ROLES:
        raise unauthenticated()
    return Principal(user_id=user_id, role=cast(Role, role), email_verified=verified != "false")


async def current_principal(request: Request) -> Principal:
    settings: Settings = request.app.state.settings
    if settings.auth_mode == "dev":
        return principal_from_dev_headers(
            request.headers.get("x-dev-user-id"),
            request.headers.get("x-dev-role"),
            request.headers.get("x-dev-email-verified"),
        )
    from arag.auth.tokens import JwksCache, http_jwks_fetch, principal_from_jwt

    scheme, _, token = (request.headers.get("authorization") or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise unauthenticated()
    cache = getattr(request.app.state, "jwks", None)
    if cache is None:
        cache = request.app.state.jwks = JwksCache(http_jwks_fetch(settings.auth_jwks_url))
    return await principal_from_jwt(
        token.strip(), cache, issuer=settings.auth_issuer, audience=settings.auth_audience
    )


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]
