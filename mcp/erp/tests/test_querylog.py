"""呼び出しごとの問い合わせの記録（specs/036 R3〜R5）。"""

import json
from typing import Any

from erp_mcp import querylog
from erp_mcp.backends.odoo import OdooBackend
from erp_mcp.model import ErpUser
from erp_mcp.tools import Service

from .test_tools import _call


def test_log_keeps_30_entries_and_4000_chars() -> None:
    with querylog.collect() as log:
        for i in range(40):
            querylog.add("sql", f"SELECT {i}" + ("x" * 5000 if i == 0 else ""))
    out = log.dump()
    assert len(out["queries"]) == 30 and out["queries_dropped"] == 10
    assert len(out["queries"][0]["text"]) == 4000
    # 入れ物の外では何もしない
    querylog.add("sql", "SELECT 1")


async def test_mock_backend_returns_sql_with_values(service: Service) -> None:
    out = await _call(service, "get_stock", part="P-1042")
    qs = out["trace"]["queries"]
    assert qs and all(q["lang"] == "sql" for q in qs)
    assert any("'P-1042'" in q["text"] for q in qs) and not any("?" in q["text"] for q in qs)
    # 使い回し（10 秒）の答えは問い合わせを発行していない
    again = await _call(service, "get_stock", part="P-1042")
    assert again["trace"]["cached"] is True and again["trace"]["queries"] == []


async def test_odoo_rpc_is_logged_without_secrets() -> None:
    sent: list[tuple[Any, ...]] = []

    class Fake(OdooBackend):
        async def _rpc(self, service: str, method: str, *args: Any) -> Any:
            sent.append((service, method, *args))
            return 7 if method == "login" else [{"id": 1}, {"id": 2}]

    be = Fake("http://odoo", "db", "top-secret-value", {})
    who = ErpUser("erp-viewer")
    with querylog.collect() as log:
        await be._x(who, "product.product", "search_read", [["default_code", "=", "P-1"]], fields=["name"], limit=80)
    q = log.dump()["queries"]
    assert len(q) == 1  # login は記録しない
    assert q[0]["lang"] == "odoo" and q[0]["rows"] == 2
    assert q[0]["text"].startswith("product.product.search_read([['default_code', '=', 'P-1']]")
    assert "fields=['name']" in q[0]["text"] and "limit=80" in q[0]["text"] and "context" not in q[0]["text"]
    dumped = json.dumps(q)
    assert "top-secret" not in dumped and "password" not in dumped
