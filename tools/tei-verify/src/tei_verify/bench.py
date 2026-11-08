"""速度とGPUメモリの目安。GPU メモリは nvidia-smi の全体使用量（他コンテナ分を含む）。"""

from __future__ import annotations

import shutil
import statistics
import subprocess
import threading
import time
from typing import Any

from tei_verify.tei import TeiClient


def gpu_mem_used_mib() -> int | None:
    if shutil.which("nvidia-smi") is None:
        return None
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return int(out.stdout.split()[0])
    except (IndexError, ValueError):
        return None


class _PeakSampler:
    def __init__(self, interval: float = 0.2) -> None:
        self.peak: int | None = None
        self._stop = threading.Event()
        self._interval = interval
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            v = gpu_mem_used_mib()
            if v is not None:
                self.peak = v if self.peak is None else max(self.peak, v)
            self._stop.wait(self._interval)

    def __enter__(self) -> _PeakSampler:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join()


def long_texts(seed_texts: list[str], *, target_chars: int, count: int) -> list[str]:
    """短い文書をつなげて長文を作る。日本語は 1 token ≒ 1〜1.5 文字なので target_chars で長さを調整する。"""
    out: list[str] = []
    i = 0
    for _ in range(count):
        buf = ""
        while len(buf) < target_chars:
            buf += seed_texts[i % len(seed_texts)] + "\n"
            i += 1
        out.append(buf[:target_chars])
    return out


def _run(fn: Any, rounds: int, batch: int, warmup: int = 2) -> dict[str, Any]:
    for _ in range(warmup):
        fn()
    before = gpu_mem_used_mib()
    times: list[float] = []
    with _PeakSampler() as sampler:
        for _ in range(rounds):
            t0 = time.perf_counter()
            fn()
            times.append(time.perf_counter() - t0)
    return {
        "batch": batch,
        "rounds": rounds,
        "docs_per_sec": batch * rounds / sum(times),
        "p50_ms": statistics.median(times) * 1000,
        "gpu_mem_before_mib": before,
        "gpu_mem_peak_mib": sampler.peak,
    }


def bench_embed(client: TeiClient, texts: list[str], *, rounds: int) -> dict[str, Any]:
    result = _run(lambda: client.embed(texts), rounds, len(texts))
    result["avg_tokens"] = statistics.mean(client.token_counts(texts))
    return result


def bench_rerank(client: TeiClient, query: str, texts: list[str], *, rounds: int) -> dict[str, Any]:
    result = _run(lambda: client.rerank(query, texts, raw_scores=True), rounds, len(texts))
    result["avg_tokens"] = statistics.mean(client.token_counts(texts))
    return result
