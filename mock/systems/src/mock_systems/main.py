"""模擬の社内システムを起動する: データを作り、4 つの MCP サーバをポートを分けて動かす（specs/032 design 全体）。

    python -m mock_systems.main
環境変数: ARAG_MCP_IDENTITY_KEY（必須）・MOCK_DATA_DIR（既定 ./data）・MOCK_TODAY・MOCK_FAULTS・MOCK_ADMIN
"""

import asyncio
import os
from pathlib import Path

import uvicorn

from mock_systems.common import identity_key
from mock_systems.seed import build
from mock_systems.servers import SYSTEMS, asgi_app


async def serve(data_dir: Path, key: str, host: str = "0.0.0.0", port_offset: int = 0) -> None:
    servers = [
        uvicorn.Server(
            uvicorn.Config(asgi_app(name, data_dir, key), host=host, port=port + port_offset, log_level="info")
        )
        for name, (_, _, port) in SYSTEMS.items()
    ]
    await asyncio.gather(*(s.serve() for s in servers))


def main() -> None:
    key = identity_key()
    data_dir = Path(os.environ.get("MOCK_DATA_DIR", "data"))
    build(data_dir)
    asyncio.run(serve(data_dir, key))


if __name__ == "__main__":
    main()
