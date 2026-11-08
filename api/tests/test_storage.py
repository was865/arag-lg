"""LocalStorage（specs/003-ingestion R12）。"""

from pathlib import Path

import pytest

from arag.storage import LocalStorage, StorageError, content_prefix

HASH = "ab" + "0" * 62


def test_content_prefix_layout() -> None:
    assert content_prefix(HASH) == f"contents/ab/{HASH}"


def test_content_prefix_rejects_non_hex() -> None:
    with pytest.raises(StorageError):
        content_prefix("../etc")


async def test_put_open_exists(tmp_path: Path) -> None:
    s = LocalStorage(tmp_path)
    key = f"{content_prefix(HASH)}/original.pdf"
    assert not await s.exists(key)
    await s.put(key, b"hello world")
    assert await s.exists(key)
    assert await s.read(key) == b"hello world"
    assert await s.size(key) == 11


async def test_open_range(tmp_path: Path) -> None:
    s = LocalStorage(tmp_path)
    await s.put("a/b.bin", b"0123456789")
    assert await s.read_range("a/b.bin", 2, 5) == b"2345"
    assert await s.read_range("a/b.bin", 8, 100) == b"89"


async def test_put_file_moves_temp(tmp_path: Path) -> None:
    s = LocalStorage(tmp_path / "root")
    src = tmp_path / "upload.tmp"
    src.write_bytes(b"x" * 10)
    await s.put_file("k/original.txt", src)
    assert await s.read("k/original.txt") == b"x" * 10


async def test_delete_prefix(tmp_path: Path) -> None:
    s = LocalStorage(tmp_path)
    await s.put("contents/ab/h/original.pdf", b"1")
    await s.put("contents/ab/h/assets/p1.png", b"2")
    await s.put("contents/ab/other/original.pdf", b"3")
    await s.delete_prefix("contents/ab/h")
    assert not await s.exists("contents/ab/h/original.pdf")
    assert await s.exists("contents/ab/other/original.pdf")
    # 無い prefix の削除はエラーにしない
    await s.delete_prefix("contents/ab/missing")


@pytest.mark.parametrize("key", ["../x", "a/../../x", "/etc/passwd", "", "a//b", "a/./b"])
async def test_rejects_escaping_keys(tmp_path: Path, key: str) -> None:
    s = LocalStorage(tmp_path)
    with pytest.raises(StorageError):
        await s.put(key, b"x")
