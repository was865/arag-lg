"""呼び出しの監査（specs/033 R11）: 1 回の呼び出しを JSON の 1 行で残す（本番は収集の仕組みへ送る）。"""

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class Audit:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.lock = threading.Lock()
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "Audit":
        raw = os.environ.get("ERP_AUDIT_PATH", "")
        return cls(Path(raw) if raw else None)

    def write(self, **entry: Any) -> None:
        line = json.dumps({"at": datetime.now(UTC).isoformat(timespec="milliseconds"), **entry}, ensure_ascii=False)
        if self.path is None:
            return
        with self.lock, self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def tail(self, n: int = 50) -> list[dict[str, Any]]:
        if self.path is None or not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-n:]
        return [json.loads(x) for x in lines if x.strip()]
