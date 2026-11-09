"""TEI（text-embeddings-inference）の /embed クライアント。バッチ分割と再試行つき。"""

import asyncio
from collections.abc import Sequence
from typing import Any, Protocol

import httpx

from arag.logging import get_logger

log = get_logger("arag.ingest.embedder")

_RETRY_STATUS = frozenset({408, 429, 500, 502, 503, 504})


class EmbedError(Exception):
    pass


class Embedder(Protocol):
    model: str

    async def dimension(self) -> int: ...
    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...
    async def embed_query(self, texts: Sequence[str]) -> list[list[float]]: ...


class TeiEmbedder:
    def __init__(
        self,
        base_url: str,
        *,
        model: str,
        batch_size: int = 32,
        timeout_sec: float = 60.0,
        max_attempts: int = 3,
        backoff_sec: float = 1.0,
        document_prefix: str = "",
        query_prefix: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.batch_size = batch_size
        self.timeout_sec = timeout_sec
        self.max_attempts = max_attempts
        self.backoff_sec = backoff_sec
        # ruri-v3 は「検索文書: 」「検索クエリ: 」を付ける。bge-m3 は空（specs/004-retrieval §2）
        self.document_prefix = document_prefix
        self.query_prefix = query_prefix
        self._transport = transport
        self._dim: int | None = None

    async def dimension(self) -> int:
        if self._dim is None:
            self._dim = len((await self.embed(["次元確認"]))[0])
        return self._dim

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """文書側の埋め込み。"""
        return await self._embed([self.document_prefix + t for t in texts])

    async def embed_query(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._embed([self.query_prefix + t for t in texts])

    async def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        async with self._client() as client:
            for i in range(0, len(texts), self.batch_size):
                out.extend(await self._batch(client, list(texts[i : i + self.batch_size])))
        return out

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_sec,
            transport=self._transport,
            headers=self._headers(),
        )

    def _headers(self) -> dict[str, str]:
        return {}

    async def _post(self, client: httpx.AsyncClient, batch: list[str]) -> httpx.Response:
        return await client.post("/embed", json={"inputs": batch, "truncate": True, "normalize": True})

    def _vectors(self, payload: object) -> list[list[float]]:
        return payload  # type: ignore[return-value]  # TEI は入力順のベクトル配列

    async def _batch(self, client: httpx.AsyncClient, batch: list[str]) -> list[list[float]]:
        last: str = ""
        for attempt in range(1, self.max_attempts + 1):
            try:
                res = await self._post(client, batch)
                if res.status_code in _RETRY_STATUS:
                    last = f"HTTP {res.status_code}: {res.text[:200]}"
                else:
                    res.raise_for_status()
                    vectors = self._vectors(res.json())
                    if len(vectors) != len(batch):
                        raise EmbedError(f"件数が一致しません: {len(vectors)} != {len(batch)}")
                    return vectors
            except httpx.TransportError as e:
                last = f"{type(e).__name__}: {e}"
            except httpx.HTTPStatusError as e:  # 4xx（再試行しても直らない）
                raise EmbedError(f"HTTP {e.response.status_code}: {e.response.text[:200]}") from e
            log.warning("embed_retry", attempt=attempt, error=last)
            if attempt < self.max_attempts:
                await asyncio.sleep(self.backoff_sec * 2 ** (attempt - 1))
        raise EmbedError(f"埋め込みに失敗しました: {last}")


class OpenAIEmbedder(TeiEmbedder):
    """OpenAI 互換の /embeddings（OpenAI・Jina・Voyage、vLLM・Infinity など。specs/016 R1）。

    base_url は版を含める（例 https://api.openai.com/v1）。
    鍵が空なら Authorization を送らない（自前サーバ向け）。
    """

    def __init__(
        self, base_url: str, *, model: str, api_key: str = "", dimensions: int = 0, **kw: Any
    ) -> None:
        super().__init__(base_url, model=model, **kw)
        self._api_key = api_key
        self.dimensions = dimensions

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

    async def _post(self, client: httpx.AsyncClient, batch: list[str]) -> httpx.Response:
        body: dict[str, Any] = {"model": self.model, "input": batch, "encoding_format": "float"}
        if self.dimensions:
            body["dimensions"] = self.dimensions
        return await client.post("/embeddings", json=body)

    def _vectors(self, payload: object) -> list[list[float]]:
        data = payload.get("data", []) if isinstance(payload, dict) else []
        # 返る順は保証されないので index で並べ直す
        return [d["embedding"] for d in sorted(data, key=lambda d: int(d["index"]))]
