"""評価題の候補を LLM で作る（specs/004-retrieval R23・C6）。人が選別してから golden.yaml にする。

uv run python -m arag.eval.synth --suite agentic_rag_demo --model deepseek:deepseek-v4-pro \\
    --out ../eval/suites/agentic_rag_demo_ext/candidates.yaml
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Literal

import yaml
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from sqlalchemy import select

from arag.db.engine import make_engine, make_sessionmaker
from arag.db.models import Document, Section
from arag.eval.__main__ import find_kb
from arag.settings import Settings

Kind = Literal["fact", "exact_id", "multi_hop", "paraphrase", "english", "cross_doc", "negative"]


class Candidate(BaseModel):
    kind: Kind
    query: str = Field(description="利用者が実際に打ちそうな質問文")
    answer: str = Field(description="文書に基づく短い正解")
    key_facts: list[list[str]] = Field(
        description="正解に必須の事実。各要素は表記ゆれの候補（いずれか 1 つが本文に出れば可）。2〜3 個"
    )
    relevant_documents: list[str] = Field(description="答えの根拠になる文書のファイル名")


class Batch(BaseModel):
    items: list[Candidate]


PER_DOC = """あなたは社内文書検索システムの評価題を作る担当者です。
次の文書だけを根拠に、検索評価用の質問を作ってください。

文書ファイル名: {name}
---
{text}
---

作る質問（合計 8 問）:
- fact ×3: 本文の具体的な値・条件を問う日本語の質問
- exact_id ×1: 型番・条項番号・コードなど識別子そのものを含む質問
- multi_hop ×1: 文書内の 2 か所（例: 表と注記、規則と例外）を組み合わせないと答えられない質問
- paraphrase ×1: 本文の語をなるべく使わず言い換えた日本語の質問
- english ×2: 英語の質問（社員が英語で尋ねる想定）

規則: 答えは必ず文書内にあること。
key_facts の候補は本文に実際に出る表記にすること。relevant_documents は ["{name}"]。"""

CROSS = """あなたは社内文書検索システムの評価題を作る担当者です。
次の複数文書を根拠に評価用の質問を作ってください。

{docs}

作る質問:
- cross_doc ×8: 2 つ以上の文書を照合しないと答えられない日本語の質問（うち 2 問は英語）。
  relevant_documents に必要な文書をすべて入れる
- negative ×5: どの文書にも答えが無いが、関係がありそうに見える質問。
  answer は「文書に記載なし」、key_facts と relevant_documents は空

規則: key_facts の候補は本文に実際に出る表記にすること。"""


JSON_SPEC = """

出力は次の形の JSON だけにすること:
{"items": [{"kind": "fact|exact_id|multi_hop|paraphrase|english|cross_doc|negative",
  "query": "質問", "answer": "短い正解", "key_facts": [["表記1", "表記2"], ["事実2"]],
  "relevant_documents": ["ファイル名"]}]}"""


async def main_async(args: argparse.Namespace) -> int:
    settings = Settings()
    kb = await find_kb(settings, args.suite)
    if kb is None:
        raise SystemExit("先に arag.eval ingest を実行してください")
    engine = make_engine(settings.database_url)
    try:
        async with make_sessionmaker(engine)() as s:
            docs = (
                await s.execute(
                    select(Document.filename, Document.content_hash)
                    .where(Document.kb_id == kb, Document.deleted_at.is_(None))
                    .order_by(Document.filename)
                )
            ).all()
            texts: dict[str, str] = {}
            for name, h in docs:
                secs = await s.scalars(
                    select(Section).where(Section.content_hash == h).order_by(Section.ordinal)
                )
                texts[name] = "\n\n".join(f"## {x.heading_path}\n{x.text}" for x in secs)
    finally:
        await engine.dispose()
    # DeepSeek の思考モードは tool_choice を受けないので JSON モードで構造化する
    model = init_chat_model(args.model).with_structured_output(Batch, method="json_mode")
    jobs = [model.ainvoke(PER_DOC.format(name=n, text=t) + JSON_SPEC) for n, t in texts.items()]
    jobs.append(
        model.ainvoke(CROSS.format(docs="\n\n".join(f"### {n}\n{t}" for n, t in texts.items())) + JSON_SPEC)
    )
    batches = await asyncio.gather(*jobs)
    out = []
    for b in batches:
        for c in b.items:
            c.relevant_documents = [d for d in c.relevant_documents if d in texts]
            out.append(c.model_dump())
    dest = Path(args.out)
    await asyncio.to_thread(dest.parent.mkdir, parents=True, exist_ok=True)
    dump = yaml.safe_dump(out, allow_unicode=True, sort_keys=False)
    await asyncio.to_thread(dest.write_text, dump, encoding="utf-8")
    print(f"候補 {len(out)} 問 → {args.out}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="arag.eval.synth")
    p.add_argument("--suite", required=True)
    p.add_argument("--model", default="deepseek:deepseek-v4-pro")
    p.add_argument("--out", required=True)
    return asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
