"""`uv run python -m tei_verify --preset bge --embed-url ... --rerank-url ...`"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from tei_verify import bench, reference
from tei_verify.data import load_corpus
from tei_verify.metrics import compare_embeddings, compare_rerank, sigmoid
from tei_verify.presets import PRESETS
from tei_verify.report import ModelResult, render_markdown
from tei_verify.tei import TeiClient


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="tei_verify", description=__doc__)
    p.add_argument("--preset", choices=sorted(PRESETS), required=True, help="接頭辞と rerank 参照実装の組")
    p.add_argument("--embed-url", required=True)
    p.add_argument("--rerank-url", required=True)
    p.add_argument("--out-dir", type=Path, default=Path("results"))
    p.add_argument("--embed-threshold", type=float, default=0.999)
    p.add_argument("--rerank-tolerance", type=float, default=1e-2)
    p.add_argument("--bench-rounds", type=int, default=10, help="0 で速度計測を省く")
    p.add_argument("--bench-batch", type=int, default=32)
    p.add_argument("--bench-chars", type=int, default=820, help="計測用長文の文字数（bge-m3 で ≒512 token）")
    return p.parse_args(argv)


def _model(info: dict[str, Any]) -> tuple[str, str | None]:
    return str(info["model_id"]), info.get("model_sha")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    preset = PRESETS[args.preset]
    corpus = load_corpus()
    doc_texts = [d.text for d in corpus.documents]
    query_ids = [q.id for q in corpus.queries]

    embed_client, rerank_client = TeiClient(args.embed_url), TeiClient(args.rerank_url)
    embed_info, rerank_info = embed_client.info(), rerank_client.info()
    embed_model, embed_rev = _model(embed_info)
    rerank_model, rerank_rev = _model(rerank_info)
    print(f"[{preset.name}] embed={embed_model}@{embed_rev} rerank={rerank_model}@{rerank_rev}")

    # embedding: クエリと文書を両方比べる（接頭辞は両者に同じく付ける）
    inputs = preset.embed_texts([q.text for q in corpus.queries], kind="query") + preset.embed_texts(
        doc_texts, kind="document"
    )
    tei_vecs = embed_client.embed(inputs)
    embed_path = reference.resolve(embed_model, embed_rev)
    ref_vecs = reference.embed(embed_path, inputs)
    embed_cmp = compare_embeddings(tei_vecs, ref_vecs, threshold=args.embed_threshold)

    # rerank: 各クエリ × 全文書
    tei_raw = {q.id: rerank_client.rerank(q.text, doc_texts, raw_scores=True) for q in corpus.queries}
    tei_sig = {q.id: rerank_client.rerank(q.text, doc_texts, raw_scores=False) for q in corpus.queries}
    pairs = [(q.text, d) for q in corpus.queries for d in doc_texts]
    rerank_path = reference.resolve(rerank_model, rerank_rev)
    flat = (
        reference.rerank_flag(rerank_path, pairs)
        if preset.rerank_impl == "flag"
        else reference.rerank_cross_encoder(rerank_path, pairs)
    )
    n = len(doc_texts)
    ref_raw = {qid: flat[i * n : (i + 1) * n] for i, qid in enumerate(query_ids)}
    ref_sig = {qid: sigmoid(np.asarray(v)).tolist() for qid, v in ref_raw.items()}

    bench_result: dict[str, Any] = {}
    if args.bench_rounds > 0:
        texts = bench.long_texts(doc_texts, target_chars=args.bench_chars, count=args.bench_batch)
        bench_result["embed"] = bench.bench_embed(
            embed_client, preset.embed_texts(texts, kind="document"), rounds=args.bench_rounds
        )
        bench_result["rerank"] = bench.bench_rerank(
            rerank_client, corpus.queries[0].text, texts, rounds=args.bench_rounds
        )

    result = ModelResult(
        preset=preset.name,
        embed_model=embed_model,
        rerank_model=rerank_model,
        embed=embed_cmp,
        rerank_raw=compare_rerank(tei_raw, ref_raw, tolerance=args.rerank_tolerance),
        rerank_sigmoid=compare_rerank(tei_sig, ref_sig, tolerance=args.rerank_tolerance),
        # TEI 1.9.4 の /info は model_sha が null のため、参照側で読んだ snapshot の commit を残す
        info={
            "embed": embed_info,
            "rerank": rerank_info,
            "reference_revision": {"embed": Path(embed_path).name, "rerank": Path(rerank_path).name},
        },
        bench=bench_result,
    )
    detail = {
        **result.to_dict(),
        "scores": {"tei_raw": tei_raw, "ref_raw": ref_raw, "tei_sigmoid": tei_sig, "ref_sigmoid": ref_sig},
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / f"{preset.name}.json").write_text(
        json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = render_markdown([result])
    (args.out_dir / f"{preset.name}.md").write_text(md, encoding="utf-8")
    print(md)
    embed_client.close()
    rerank_client.close()
    return 0 if result.passed else 1
