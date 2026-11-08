"""同梱の日本語評価データ（data/corpus.json）の読み込み。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CORPUS = Path(__file__).resolve().parents[2] / "data" / "corpus.json"


@dataclass(frozen=True)
class Document:
    id: str
    kind: str
    text: str


@dataclass(frozen=True)
class Query:
    id: str
    text: str
    relevant: list[str]


@dataclass(frozen=True)
class Corpus:
    documents: list[Document]
    queries: list[Query]


def load_corpus(path: Path = DEFAULT_CORPUS) -> Corpus:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Corpus(
        documents=[Document(**d) for d in raw["documents"]],
        queries=[Query(**q) for q in raw["queries"]],
    )
