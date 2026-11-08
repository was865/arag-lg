"""公開データセットから評価題集を作る（specs/004-retrieval R23）。

データは eval/.cache/<suite>/ に置き、リポジトリには入れない。設定は eval/suites/<suite>/suite.yaml。

- beir:  BEIR 形式の zip（corpus.jsonl / queries.jsonl / qrels/<split>.tsv）。旧版 rag/eval/beir.py の移植
- jqara: hotchpotch/JQaRA（CC-BY-SA 4.0）。HF の datasets-server から行を取り、質問ごとの候補文を
         すべてコーパスに入れる（他の質問の候補が紛らわしい負例になる）。answers を key_facts にする
"""

import ast
import io
import json
import re
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import yaml

_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")
ROWS_API = "https://datasets-server.huggingface.co/rows"


def _filename(prefix: str, docid: str) -> str:
    return f"{prefix}{_SAFE.sub('_', docid).strip('._') or 'doc'}.md"


def _body(title: str, text: str) -> str:
    title, text = title.strip(), text.strip()
    return f"# {title}\n\n{text}\n" if title else f"{text}\n"


# ---- BEIR


def read_jsonl(data: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for line in data.splitlines():
        if line.strip():
            row = json.loads(line)
            out[str(row["_id"])] = row
    return out


def read_qrels(data: str) -> dict[str, set[str]]:
    qrels: dict[str, set[str]] = {}
    for line in data.splitlines():
        parts = line.strip().split()
        if len(parts) < 3 or parts[0].lower() in {"query-id", "query_id", "qid"}:
            continue
        try:
            relevant = float(parts[-1]) > 0
        except ValueError:
            relevant = False
        if relevant:
            qrels.setdefault(parts[0], set()).add(parts[1])
    return qrels


def build_beir(
    corpus: dict[str, dict[str, Any]],
    queries: dict[str, dict[str, Any]],
    qrels: dict[str, set[str]],
    cfg: dict[str, Any],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """(ファイル名 → 本文, ケース)。コーパスは関連文書 + ID 順の先頭で corpus_limit 件まで。"""
    qids = [q for q in sorted(qrels) if q in queries and qrels[q]]
    if cfg.get("query_limit"):
        qids = qids[: cfg["query_limit"]]
    selected = sorted({d for q in qids for d in qrels[q] if d in corpus})
    limit = cfg.get("corpus_limit") or len(corpus)
    for d in sorted(corpus):
        if len(selected) >= limit:
            break
        if d not in selected:
            selected.append(d)
    names = {d: _filename("", d) for d in selected}
    files = {names[d]: _body(corpus[d].get("title") or "", corpus[d].get("text") or "") for d in selected}
    cases = [
        {
            "id": f"{cfg['dataset']}-{q}",
            "query": queries[q]["text"],
            "top_k": 10,
            "tags": ["en", "beir", cfg["dataset"]],
            "relevant_documents": sorted(names[d] for d in qrels[q] if d in names),
            "key_facts": [],
        }
        for q in qids
    ]
    return files, [c for c in cases if c["relevant_documents"]]


def _prepare_beir(cfg: dict[str, Any], cache: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    zip_path = cache / Path(cfg["source_url"]).name
    if not zip_path.exists():
        print(f"取得中: {cfg['source_url']}")
        with httpx.stream("GET", cfg["source_url"], timeout=600, follow_redirects=True) as r:
            r.raise_for_status()
            zip_path.write_bytes(b"".join(r.iter_bytes()))
    with zipfile.ZipFile(zip_path) as zf:

        def read(name: str) -> str:
            path = next(n for n in zf.namelist() if n.endswith(name))
            return io.TextIOWrapper(zf.open(path), encoding="utf-8").read()

        corpus = read_jsonl(read("corpus.jsonl"))
        queries = read_jsonl(read("queries.jsonl"))
        qrels = read_qrels(read(f"qrels/{cfg.get('split', 'test')}.tsv"))
    return build_beir(corpus, queries, qrels, cfg)


# ---- JQaRA


def build_jqara(
    rows: list[dict[str, Any]], cfg: dict[str, Any]
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    by_q: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_q.setdefault(r["q_id"], []).append(r)
    files: dict[str, str] = {}
    cases: list[dict[str, Any]] = []
    for qid, items in by_q.items():
        for r in items:
            files[_filename("jqara-", str(r["passage_row_id"]))] = _body(r.get("title") or "", r["text"])
        relevant = sorted(
            {_filename("jqara-", str(r["passage_row_id"])) for r in items if str(r["label"]) == "1"}
        )
        if not relevant:
            continue
        answers = items[0]["answers"]
        if isinstance(answers, str):
            answers = ast.literal_eval(answers)
        cases.append(
            {
                "id": f"jqara-{qid}",
                "query": items[0]["question"],
                "top_k": 10,
                "tags": ["ja", "jqara"],
                "relevant_documents": relevant,
                "key_facts": [{"any": [str(a) for a in answers]}] if answers else [],
            }
        )
    return files, cases


def _jqara_rows(cfg: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """質問 query_limit 件ぶんの行（行は質問ごとに連続して並ぶ）。"""
    want = cfg.get("query_limit") or 100
    seen: list[str] = []
    offset = 0
    with httpx.Client(timeout=60) as c:
        while True:
            res = c.get(
                ROWS_API,
                params={
                    "dataset": cfg["dataset"],
                    "config": "default",
                    "split": cfg.get("split", "test"),
                    "offset": offset,
                    "length": 100,
                },
            )
            res.raise_for_status()
            rows = [x["row"] for x in res.json()["rows"]]
            if not rows:
                return
            for r in rows:
                if r["q_id"] not in seen:
                    if len(seen) >= want:
                        return
                    seen.append(r["q_id"])
                yield r
            offset += len(rows)
            if offset % 2000 == 0:
                print(f"  {offset} 行（質問 {len(seen)} 件）")


def prepare(root: Path, suite: str) -> int:
    cfg = yaml.safe_load((root / "eval" / "suites" / suite / "suite.yaml").read_text(encoding="utf-8"))
    cache = root / "eval" / ".cache" / suite
    files_dir = cache / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    if cfg["adapter"] == "beir":
        files, cases = _prepare_beir(cfg, cache)
    elif cfg["adapter"] == "jqara":
        files, cases = build_jqara(list(_jqara_rows(cfg)), cfg)
    else:
        raise SystemExit(f"未知の adapter: {cfg['adapter']}")
    for name, body in files.items():
        (files_dir / name).write_text(body, encoding="utf-8")
    golden = {
        "suite": suite,
        "files_dir": "files",
        "documents": sorted(files),
        "thresholds": cfg.get("thresholds") or {},
        "cases": cases,
    }
    (cache / "golden.yaml").write_text(
        yaml.safe_dump(golden, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    print(f"{suite}: 文書 {len(files)} 件・質問 {len(cases)} 件 → {cache}")
    return 0
