"""参照実装（sentence-transformers / FlagEmbedding）。CPU・fp32 で計算する。

TEI の /info が返す model_sha と同じ revision を読み込み、重みの差を比較から除く。
torch の import が重いので、このモジュールは必要時にだけ読み込む。
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def resolve(model_id: str, revision: str | None) -> str:
    from huggingface_hub import snapshot_download

    return snapshot_download(model_id, revision=revision)


def embed(path: str, texts: list[str]) -> NDArray[np.float64]:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(path, device="cpu")
    out = model.encode(texts, batch_size=8, normalize_embeddings=True, convert_to_numpy=True)
    return np.asarray(out, dtype=np.float64)


def rerank_flag(path: str, pairs: list[tuple[str, str]]) -> list[float]:
    """FlagEmbedding の FlagReranker（bge-reranker 公式の参照実装）。生の logit を返す。"""
    from FlagEmbedding import FlagReranker

    model = FlagReranker(path, use_fp16=False, devices="cpu")
    scores = model.compute_score([list(p) for p in pairs], normalize=False)
    return [float(s) for s in np.atleast_1d(scores)]


def rerank_cross_encoder(path: str, pairs: list[tuple[str, str]]) -> list[float]:
    """sentence-transformers の CrossEncoder。活性化関数を外して生の logit を返す。"""
    import torch
    from sentence_transformers import CrossEncoder

    model = CrossEncoder(path, device="cpu")
    scores = model.predict(pairs, batch_size=8, activation_fn=torch.nn.Identity(), convert_to_numpy=True)
    return [float(s) for s in np.atleast_1d(scores)]
