"""ファイルストレージ（specs/000-overview/data-model.md §6、R12）。

キーは `/` 区切りの相対パス。root の外へ出るキーは拒否する。S3 互換は後続。
"""

import asyncio
import os
import re
import shutil
from pathlib import Path
from typing import Protocol

_HASH = re.compile(r"^[0-9a-f]{64}$")


class StorageError(ValueError):
    pass


def content_prefix(content_hash: str) -> str:
    if not _HASH.match(content_hash):
        raise StorageError("不正な内容ハッシュです")
    return f"contents/{content_hash[:2]}/{content_hash}"


class Storage(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...
    async def put_file(self, key: str, src: Path) -> None: ...
    async def read(self, key: str) -> bytes: ...
    async def read_range(self, key: str, start: int, end: int) -> bytes: ...
    async def size(self, key: str) -> int: ...
    async def exists(self, key: str) -> bool: ...
    async def delete_prefix(self, prefix: str) -> None: ...
    async def delete(self, key: str) -> None: ...
    def local_path(self, key: str) -> Path | None: ...


class LocalStorage:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        parts = key.split("/")
        if not key or key.startswith("/") or any(p in ("", ".", "..") for p in parts):
            raise StorageError(f"不正なキーです: {key!r}")
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise StorageError(f"不正なキーです: {key!r}")
        return path

    def local_path(self, key: str) -> Path | None:
        return self._path(key)

    async def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        await asyncio.to_thread(_atomic_write, path, data)

    async def put_file(self, key: str, src: Path) -> None:
        path = self._path(key)

        def move() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(src, path)

        await asyncio.to_thread(move)

    async def read(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def read_range(self, key: str, start: int, end: int) -> bytes:
        """start〜end（両端含む）を読む。HTTP Range と同じ数え方。"""
        path = self._path(key)

        def read() -> bytes:
            with path.open("rb") as f:
                f.seek(start)
                return f.read(max(0, end - start + 1))

        return await asyncio.to_thread(read)

    async def size(self, key: str) -> int:
        return (await asyncio.to_thread(self._path(key).stat)).st_size

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._path(key).is_file)

    async def delete_prefix(self, prefix: str) -> None:
        path = self._path(prefix)
        await asyncio.to_thread(shutil.rmtree, path, True)

    async def delete(self, key: str) -> None:
        """1 つのファイルを消す（無ければ何もしない）。"""
        await asyncio.to_thread(self._path(key).unlink, True)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
