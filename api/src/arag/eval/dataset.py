"""評価題集（golden.yaml）。旧版 rag/eval/dataset.py を移植。"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator


class KeyFact(BaseModel):
    any: list[str]  # いずれか 1 つが結果本文（+ 親セクション）に出れば充足


class Case(BaseModel):
    id: str
    query: str
    rewritten: str | None = None
    top_k: int = 6
    tags: list[str] = Field(default_factory=list)  # 言語は ja / en / cross（日英をまたぐ）
    relevant_documents: list[str] = Field(default_factory=list)
    key_facts: list[KeyFact] = Field(default_factory=list)


class Thresholds(BaseModel):
    recall_at_5: float | None = None
    fact_coverage: float | None = None
    ndcg_at_k: float | None = None


class GoldenSuite(BaseModel):
    suite: str
    owner_user_id: str | None = None  # 旧版互換（新版は KB「評価: <suite>」で分ける）
    files_dir: str | None = None
    documents: list[str]
    thresholds: Thresholds = Thresholds()
    cases: list[Case]

    @model_validator(mode="after")
    def _check_relevant_subset(self) -> "GoldenSuite":
        known = set(self.documents)
        for case in self.cases:
            for fn in case.relevant_documents:
                if fn not in known:
                    raise ValueError(f"case {case.id}: relevant_documents に未登録の {fn} があります")
        return self


def load_suite(path: str | Path) -> GoldenSuite:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return GoldenSuite.model_validate(data)
