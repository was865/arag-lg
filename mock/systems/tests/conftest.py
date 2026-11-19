from pathlib import Path

import pytest

from mock_systems.common import Identity, open_ro
from mock_systems.seed import build

ASSETS = Path(__file__).resolve().parents[3] / "eval" / "assets" / "harukaze_mix" / "docs"
KEY = "test-key-0123456789abcdef0123456789"


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("mock-data")
    build(d)
    return d


@pytest.fixture
def con(data_dir: Path):  # type: ignore[no-untyped-def]
    def _open(name: str):  # type: ignore[no-untyped-def]
        return open_ro(data_dir / f"{name}.db")

    return _open


def who(*depts: str) -> Identity:
    return Identity(user_id="u-test", depts=frozenset(depts))
