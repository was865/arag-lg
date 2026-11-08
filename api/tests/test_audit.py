"""監査ログ（specs/003-ingestion R36）。"""

from typing import Any

from arag.audit import AuditEvent, build_audit_row
from arag.auth.principal import Principal


def test_build_audit_row_from_principal() -> None:
    p = Principal(user_id="u1", role="admin", email="a@example.com")
    row: dict[str, Any] = build_audit_row(
        AuditEvent(action="document.delete", resource_type="document", resource_id="d1"),
        principal=p,
        request_id="req-1",
        ip="10.0.0.1",
    )
    assert row["actor_id"] == "u1"
    assert row["actor_email"] == "a@example.com"
    assert row["action"] == "document.delete"
    assert row["result"] == "ok"
    assert row["request_id"] == "req-1"


def test_build_audit_row_system_actor() -> None:
    row = build_audit_row(AuditEvent(action="gc.purge", result="ok", detail={"contents": 2}))
    assert row["actor_id"] is None
    assert row["detail"] == {"contents": 2}
