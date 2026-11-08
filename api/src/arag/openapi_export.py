"""OpenAPI 文書を api/openapi.json に書き出す（web の型生成の入力）。

使い方: uv run python -m arag.openapi_export [出力パス]
"""

import json
import sys
from pathlib import Path

from arag.main import create_app
from arag.settings import Settings

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "openapi.json"


def render_openapi() -> str:
    app = create_app(settings=Settings(), checks=[])
    # キー順を固定し、生成物の差分が実装変更だけを表すようにする
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def export_openapi(out: Path = DEFAULT_OUT) -> None:
    out.write_text(render_openapi(), encoding="utf-8")


if __name__ == "__main__":
    export_openapi(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT)
