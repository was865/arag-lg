"""利用者（Principal）の解決（specs/003-ingestion R1・R2）。

P1 は開発用ヘッダのみ。P4 で Better Auth の JWT（JWKS 検証）を追加する。
"""

from dataclasses import dataclass
from typing import Annotated, Literal, cast

from fastapi import Depends, Request

from arag.errors import ApiError
from arag.settings import Settings

Role = Literal["owner", "admin", "member"]
_ROLES: frozenset[str] = frozenset({"owner", "admin", "member"})


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    role: Role = "member"
    email: str | None = None
    email_verified: bool = True

    @property
    def is_admin(self) -> bool:
        return self.role in ("owner", "admin")


def _unauthenticated() -> ApiError:
    return ApiError(401, "unauthenticated", "ログインが必要です")


def principal_from_dev_headers(user_id: str | None, role: str | None) -> Principal:
    if not user_id or len(user_id) > 64:
        raise _unauthenticated()
    role = role or "member"
    if role not in _ROLES:
        raise _unauthenticated()
    return Principal(user_id=user_id, role=cast(Role, role))


async def current_principal(request: Request) -> Principal:
    settings: Settings = request.app.state.settings
    if settings.auth_mode == "dev":
        return principal_from_dev_headers(
            request.headers.get("x-dev-user-id"), request.headers.get("x-dev-role")
        )
    # jwt は P4 で実装する。それまでは dev 以外では誰も通さない。
    raise _unauthenticated()


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]
