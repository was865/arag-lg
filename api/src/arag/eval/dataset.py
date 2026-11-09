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
    # 答えに書いてはいけない誤りの値（例: 一部の集計で表全体の合計）。key_facts は正しい値を含むかしか見ないので別に見る（specs/021）
    wrong_facts: list[KeyFact] = Field(default_factory=list)
    answer: str | None = None  # 参考解答（検索評価では使わない。P3 の回答評価用）
    # 文書に答えが無い題。回答評価では「資料に無い」と答えるか回答不能なら事実網羅 1.0、答えを作ったら 0.0
    expect_no_answer: bool = False
    # 続けて尋ねる題（specs/018 R4）。同じスレッドで先に尋ねる質問を順に並べる。採点は query だけ
    turns: list[str] = Field(default_factory=list)


class Thresholds(BaseModel):
    recall_at_5: float | None = None
    fact_coverage: float | None = None
    ndcg_at_k: float | None = None


class GoldenSuite(BaseModel):
    suite: str
    owner_user_id: str | None = None  # 旧版互換（新版は KB「評価: <suite>」で分ける）
    files_dir: str | None = None
    kb_suite: str | None = None  # 別の題集の KB をそのまま使う（訳した題集など）
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
