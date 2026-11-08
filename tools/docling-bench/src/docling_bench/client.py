"""docling-serve の非同期変換 API クライアント。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


def build_form(options: dict[str, Any]) -> list[tuple[str, str]]:
    """multipart のフォーム項目。リストは同じキーを繰り返す（page_range=1, page_range=20 の形）。"""
    form: list[tuple[str, str]] = []
    for key, value in options.items():
        if value is None:
            continue
        for v in value if isinstance(value, list | tuple) else [value]:
            form.append((key, str(v).lower() if isinstance(v, bool) else str(v)))
    return form


@dataclass(frozen=True)
class ConvertResult:
    task_id: str
    elapsed_sec: float
    status: str
    body: bytes

    def json(self) -> dict[str, Any]:
        import json

        data: dict[str, Any] = json.loads(self.body)
        return data


class DoclingClient:
    def __init__(self, base_url: str, *, timeout: float = 60.0) -> None:
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def convert_file(
        self, path: Path, options: dict[str, Any], *, poll_interval: float = 0.5, deadline_sec: float = 1800
    ) -> ConvertResult:
        """投入 → 完了までポーリング → 結果取得。所要時間は投入から結果取得完了まで。"""
        t0 = time.perf_counter()
        # httpx は files と併用時に (key, value) の列を受け付けないため、キーごとのリストにまとめる
        data: dict[str, list[str]] = {}
        for key, value in build_form(options):
            data.setdefault(key, []).append(value)
        with path.open("rb") as f:
            resp = self._http.post(
                "/v1/convert/file/async", data=data, files={"files": (path.name, f, "application/pdf")}
            )
        resp.raise_for_status()
        task_id = str(resp.json()["task_id"])
        status = "pending"
        while time.perf_counter() - t0 < deadline_sec:
            poll = self._http.get(f"/v1/status/poll/{task_id}", params={"wait": 5})
            poll.raise_for_status()
            status = str(poll.json()["task_status"])
            if status in ("success", "failure", "partial_success"):
                break
            time.sleep(poll_interval)
        result = self._http.get(f"/v1/result/{task_id}")
        return ConvertResult(
            task_id=task_id, elapsed_sec=time.perf_counter() - t0, status=status, body=result.content
        )
