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
    # 同じ事実を載せた別の資料。引用しても誤りでない
    # （引用精度では当たりに数え、再現率には入れない。specs/026 T23）
    acceptable_documents: list[str] = Field(default_factory=list)
    key_facts: list[KeyFact] = Field(default_factory=list)
    # 答えに書いてはいけない誤りの値（例: 一部の集計で表全体の合計）。
    # key_facts は正しい値を含むかしか見ないので別に見る（specs/021）
    wrong_facts: list[KeyFact] = Field(default_factory=list)
    answer: str | None = None  # 参考解答（検索評価では使わない。P3 の回答評価用）
    # 文書に答えが無い題。回答評価では「資料に無い」と答えるか回答不能なら事実網羅 1.0、答えを作ったら 0.0
    expect_no_answer: bool = False
    # 続けて尋ねる題（specs/018 R4）。同じスレッドで先に尋ねる質問を順に並べる。採点は query だけ
    turns: list[str] = Field(default_factory=list)
    # 聞き返すべき題か（specs/031 T12）。True: 聞き返せば正解（事実網羅 1.0）。False: 聞き返さずに答えるべき。
    # None: 聞き返しを見ない（聞き返しの率にだけ数える）
    expect_clarify: bool | None = None
    # 社内システムの題（specs/032 R27・R29）
    # as_user: 尋ねる利用者（題集の users.yaml の鍵）。省略は評価の管理者
    as_user: str | None = None
    # 題の間だけ模擬のシステムに起こす障害（例 {"cmms": "down"}）。終わったら戻す
    faults: dict[str, str] = Field(default_factory=dict)
    # 呼ぶべき社内システム（サーバ名）。全部呼べば当たり。「cmms|tickets」はどちらかを呼べばよい
    expect_tools: list[str] = Field(default_factory=list)
    # 答えに出てはいけない値（権限の無い人への仕入単価など）。出たら漏れ
    must_not: list[KeyFact] = Field(default_factory=list)
    # 答えに書くべき注意（時点・権限・止まっていること）。すべて満たせば当たり
    expect_caveat: list[KeyFact] = Field(default_factory=list)


class Thresholds(BaseModel):
    recall_at_5: float | None = None
    fact_coverage: float | None = None
    ndcg_at_k: float | None = None


class GoldenSuite(BaseModel):
    suite: str
    owner_user_id: str | None = None  # 旧版互換（新版は KB「評価: <suite>」で分ける）
    files_dir: str | None = None
    kb_suite: str | None = None  # 別の題集の KB をそのまま使う（訳した題集など）
    users: str | None = None  # 題の as_user を引く利用者の定義（リポジトリからの相対パス。specs/032）
    documents: list[str]
    thresholds: Thresholds = Thresholds()
    cases: list[Case]

    @model_validator(mode="after")
    def _check_relevant_subset(self) -> "GoldenSuite":
        known = set(self.documents)
        for case in self.cases:
            for field in ("relevant_documents", "acceptable_documents"):
                for fn in getattr(case, field):
                    if fn not in known:
                        raise ValueError(f"case {case.id}: {field} に未登録の {fn} があります")
        return self


def load_suite(path: str | Path) -> GoldenSuite:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return GoldenSuite.model_validate(data)
