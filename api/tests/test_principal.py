"""Principal の解決（specs/003-ingestion R1・R2）。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from arag.auth.principal import CurrentPrincipal
from arag.errors import install_error_handlers
from arag.settings import Settings


def _client(mode: str) -> TestClient:
    app = FastAPI()
    app.state.settings = Settings(auth_mode=mode)  # type: ignore[arg-type]
    install_error_handlers(app)

    @app.get("/me")
    async def me(p: CurrentPrincipal) -> dict[str, object]:
        return {"user_id": p.user_id, "role": p.role, "is_admin": p.is_admin}

    return TestClient(app)


def test_dev_headers_become_principal() -> None:
    res = _client("dev").get("/me", headers={"X-Dev-User-Id": "u1", "X-Dev-Role": "admin"})
    assert res.status_code == 200
    assert res.json() == {"user_id": "u1", "role": "admin", "is_admin": True}


def test_dev_role_defaults_to_member() -> None:
    res = _client("dev").get("/me", headers={"X-Dev-User-Id": "u2"})
    assert res.json()["role"] == "member"
    assert res.json()["is_admin"] is False


def test_owner_counts_as_admin() -> None:
    res = _client("dev").get("/me", headers={"X-Dev-User-Id": "u3", "X-Dev-Role": "owner"})
    assert res.json()["is_admin"] is True


def test_missing_user_is_401_with_error_shape() -> None:
    res = _client("dev").get("/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "unauthenticated"


def test_invalid_role_is_401() -> None:
    res = _client("dev").get("/me", headers={"X-Dev-User-Id": "u1", "X-Dev-Role": "root"})
    assert res.status_code == 401


def test_dev_headers_ignored_outside_dev_mode() -> None:
    res = _client("jwt").get("/me", headers={"X-Dev-User-Id": "u1", "X-Dev-Role": "admin"})
    assert res.status_code == 401
