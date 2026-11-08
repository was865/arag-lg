"""モデル系列ごとの設定（接頭辞と rerank の参照実装）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TextKind = Literal["query", "document"]


@dataclass(frozen=True)
class Preset:
    name: str
    query_prefix: str
    document_prefix: str
    # rerank の参照実装: FlagEmbedding の FlagReranker か sentence-transformers の CrossEncoder
    rerank_impl: Literal["flag", "cross_encoder"]

    def embed_texts(self, texts: list[str], *, kind: TextKind) -> list[str]:
        prefix = self.query_prefix if kind == "query" else self.document_prefix
        return [prefix + t for t in texts]


PRESETS: dict[str, Preset] = {
    "bge": Preset(name="bge", query_prefix="", document_prefix="", rerank_impl="flag"),
    # ruri-v3 の埋め込みは接頭辞が必須（モデルカード）。reranker は接頭辞なし
    "ruri": Preset(
        name="ruri", query_prefix="検索クエリ: ", document_prefix="検索文書: ", rerank_impl="cross_encoder"
    ),
}
