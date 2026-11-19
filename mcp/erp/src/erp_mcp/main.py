"""ERP の MCP サーバを起動する（specs/033）。

    python -m erp_mcp.main
環境変数: ERP_BACKEND（odoo / mock）・ARAG_MCP_IDENTITY_KEY か ERP_IDENTITY_KEYS・ERP_TODAY・ERP_AUDIT_PATH・
  Odoo: ERP_ODOO_URL・ERP_ODOO_DB・ERP_ODOO_SECRET／模擬: ERP_MOCK_DB・
  ERP_TIMEOUT_S（8）・ERP_CONCURRENCY（4）・ERP_CACHE_S（10）
"""

import os
import sys
from pathlib import Path

import uvicorn

from erp_mcp import config
from erp_mcp.audit import Audit
from erp_mcp.identity import keys_from_env
from erp_mcp.model import ErpBackend
from erp_mcp.ops import Guard, TtlCache
from erp_mcp.server import asgi_app
from erp_mcp.tools import Service


def build_backend(kind: str) -> tuple[ErpBackend, list[str], str]:
    if kind == "mock":
        from erp_mcp.backends.mock import MockBackend

        c = config.load("mock")
        return MockBackend(Path(c["db"]), c["rights"], c["usable_warehouses"]), c["usable_warehouses"], "ERP（模擬）"
    if kind == "odoo":
        from erp_mcp.backends.odoo import OdooBackend

        c = config.load("odoo")
        return OdooBackend.from_config(c), c["usable_warehouses"], "ERP（Odoo）"
    raise SystemExit(f"ERP_BACKEND が不正です: {kind}")


def main() -> None:
    keys = keys_from_env()
    if not keys:
        print("ARAG_MCP_IDENTITY_KEY（か ERP_IDENTITY_KEYS）を設定してください", file=sys.stderr)
        raise SystemExit(2)
    backend, usable, label = build_backend(os.environ.get("ERP_BACKEND", "odoo"))
    service = Service(
        backend,
        config.user_map(),
        Audit.from_env(),
        label=label,
        guard=Guard(
            timeout_s=float(os.environ.get("ERP_TIMEOUT_S", 8)),
            concurrency=int(os.environ.get("ERP_CONCURRENCY", 4)),
        ),
        cache=TtlCache(float(os.environ.get("ERP_CACHE_S", 10))),
        usable=usable,
    )
    uvicorn.run(asgi_app(service, keys, label=label), host="0.0.0.0", port=int(os.environ.get("PORT", 8211)))


if __name__ == "__main__":
    main()
