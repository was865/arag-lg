from pathlib import Path

import pytest

from erp_mcp import config
from erp_mcp.audit import Audit
from erp_mcp.backends.mock import MockBackend
from erp_mcp.identity import Identity
from erp_mcp.tools import Service

WORLD = Path(__file__).resolve().parents[3] / "eval" / "assets" / "harukaze_plant" / "world.db"
KEY = "test-key-0123456789abcdef0123456789"


def who(*depts: str) -> Identity:
    return Identity("u-test", frozenset(depts), "k1")


@pytest.fixture
def mock_backend() -> MockBackend:
    c = config.load("mock")
    return MockBackend(WORLD, c["rights"], c["usable_warehouses"])


@pytest.fixture
def service(mock_backend: MockBackend, tmp_path: Path) -> Service:
    return Service(mock_backend, config.user_map(), Audit(tmp_path / "audit.jsonl"), label="ERP（模擬）")
