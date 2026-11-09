"""TEI の /rerank クライアント（specs/004-retrieval design §5）。"""

import asyncio
from collections.abc import Sequence
from typing import Any, Protocol

import httpx

from arag.logging import get_logger

log = get_logger("arag.search.rerank")

_RETRY_STATUS = frozenset({408, 429, 500, 502, 503, 504})


class RerankError(Exception):
    pass


class Reranker(Protocol):
    model: str

    async def rerank(self, query: str, texts: Sequence[str]) -> list[float]:
        """texts と同じ順のスコア（0〜1、大きいほど関連）。"""
        ...


class TeiReranker:
    def __init__(
        self,
        base_url: str,
        *,
        model: str = "cl-nagoya/ruri-v3-reranker-310m",
        batch_size: int = 32,  # TEI の --max-client-batch-size 既定
        timeout_sec: float = 10.0,
        max_attempts: int = 3,
        backoff_sec: float = 0.3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.batch_size = batch_size
        self.timeout_sec = timeout_sec
        self.max_attempts = max_attempts
        self.backoff_sec = backoff_sec
        self._transport = transport

    async def rerank(self, query: str, texts: Sequence[str]) -> list[float]:
        if not texts:
            return []
        scores: list[float] = []
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_sec,
            transport=self._transport,
            headers=self._headers(),
        ) as client:
            for i in range(0, len(texts), self.batch_size):
                scores.extend(await self._batch(client, query, list(texts[i : i + self.batch_size])))
        return scores

    def _headers(self) -> dict[str, str]:
        return {}

    async def _post(self, client: httpx.AsyncClient, query: str, texts: list[str]) -> httpx.Response:
        return await client.post(
            "/rerank", json={"query": query, "texts": texts, "raw_scores": False, "truncate": True}
        )

    def _scores(self, payload: Any) -> list[tuple[int, float]]:
        return [(int(r["index"]), float(r["score"])) for r in payload]

    async def _batch(self, client: httpx.AsyncClient, query: str, texts: list[str]) -> list[float]:
        last = ""
        for attempt in range(1, self.max_attempts + 1):
            try:
                res = await self._post(client, query, texts)
                if res.status_code in _RETRY_STATUS:
                    last = f"HTTP {res.status_code}: {res.text[:200]}"
                else:
                    res.raise_for_status()
                    out = [0.0] * len(texts)
                    seen = 0
                    for idx, score in self._scores(res.json()):  # スコア降順で返るので index で元の順に戻す
                        out[idx] = score
                        seen += 1
                    if seen != len(texts):
                        raise RerankError(f"件数が一致しません: {seen} != {len(texts)}")
                    return out
            except httpx.TransportError as e:
                last = f"{type(e).__name__}: {e}"
            except httpx.HTTPStatusError as e:
                raise RerankError(f"HTTP {e.response.status_code}: {e.response.text[:200]}") from e
            log.warning("rerank_retry", attempt=attempt, error=last)
            if attempt < self.max_attempts:
                await asyncio.sleep(self.backoff_sec * 2 ** (attempt - 1))
        raise RerankError(f"再順位付けに失敗しました: {last}")


class CohereReranker(TeiReranker):
    """Cohere 互換の /rerank（Cohere・Jina・Voyage、vLLM など。specs/016 R2）。

    base_url は版を含める（例 https://api.cohere.com/v2）。応答は results（Cohere・Jina）か data（Voyage）。
    """

    def __init__(self, base_url: str, *, model: str, api_key: str = "", **kw: Any) -> None:
        super().__init__(base_url, model=model, **kw)
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

    async def _post(self, client: httpx.AsyncClient, query: str, texts: list[str]) -> httpx.Response:
        body = {"model": self.model, "query": query, "documents": texts, "top_n": len(texts)}
        return await client.post("/rerank", json=body)

    def _scores(self, payload: Any) -> list[tuple[int, float]]:
        rows = (payload.get("results") or payload.get("data") or []) if isinstance(payload, dict) else []
        return [(int(r["index"]), float(r["relevance_score"])) for r in rows]
