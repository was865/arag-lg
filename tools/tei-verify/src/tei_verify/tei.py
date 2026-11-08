"""TEI HTTP API の薄いクライアント。"""

from __future__ import annotations

from typing import Any

import httpx
import numpy as np
from numpy.typing import NDArray

# TEI の既定 --max-client-batch-size（32）に合わせる
CLIENT_BATCH = 32


class TeiClient:
    def __init__(self, base_url: str, *, timeout: float = 120.0) -> None:
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def info(self) -> dict[str, Any]:
        resp = self._http.get("/info")
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data

    def embed(self, texts: list[str], *, normalize: bool = True) -> NDArray[np.float64]:
        rows: list[list[float]] = []
        for i in range(0, len(texts), CLIENT_BATCH):
            # truncate=False: 上限超過は黙って切らずにエラーにする（比較の前提が崩れるため）
            resp = self._http.post(
                "/embed",
                json={"inputs": texts[i : i + CLIENT_BATCH], "normalize": normalize, "truncate": False},
            )
            resp.raise_for_status()
            rows.extend(resp.json())
        return np.asarray(rows, dtype=np.float64)

    def rerank(self, query: str, texts: list[str], *, raw_scores: bool) -> list[float]:
        """文書の入力順に並べたスコアを返す（TEI はスコア降順で返すため並べ直す）。"""
        resp = self._http.post(
            "/rerank",
            json={"query": query, "texts": texts, "raw_scores": raw_scores, "truncate": False},
        )
        resp.raise_for_status()
        scores = [0.0] * len(texts)
        for item in resp.json():
            scores[item["index"]] = float(item["score"])
        return scores

    def token_counts(self, texts: list[str]) -> list[int]:
        counts: list[int] = []
        for i in range(0, len(texts), CLIENT_BATCH):
            resp = self._http.post("/tokenize", json={"inputs": texts[i : i + CLIENT_BATCH]})
            resp.raise_for_status()
            counts.extend(len(tokens) for tokens in resp.json())
        return counts
