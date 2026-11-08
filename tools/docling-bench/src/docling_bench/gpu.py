"""nvidia-smi による GPU 全体メモリのサンプリング（他プロセス分を含む）。"""

from __future__ import annotations

import shutil
import subprocess
import threading


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


class PeakSampler:
    def __init__(self, interval: float = 0.2) -> None:
        self.before = gpu_mem_used_mib()
        self.peak: int | None = self.before
        self._stop = threading.Event()
        self._interval = interval
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            v = gpu_mem_used_mib()
            if v is not None:
                self.peak = v if self.peak is None else max(self.peak, v)
            self._stop.wait(self._interval)

    def __enter__(self) -> PeakSampler:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join()
