"""docling-serve の計測。

uv run python -m docling_bench convert --url http://localhost:5001 ../../eval/assets/agentic_rag_demo/*.pdf
uv run python -m docling_bench make-scans --out scans <元 PDF ...>
uv run python -m docling_bench ocr --url http://localhost:5001 --originals <元 PDF ...> --scans scans
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from docling_bench.client import DoclingClient
from docling_bench.gpu import PeakSampler
from docling_bench.scans import make_scanned_pdf
from docling_bench.textmatch import char_accuracy, normalize

# specs/003-ingestion G1 の計測条件
CONVERT_OPTIONS: dict[str, Any] = {
    "to_formats": ["json", "md"],
    "image_export_mode": "embedded",
    "do_ocr": True,
    "ocr_lang": ["ja", "en"],
    "do_table_structure": True,
}

# OCR 比較の候補。言語指定は各エンジンの書式に合わせる
OCR_CANDIDATES: dict[str, dict[str, Any]] = {
    "easyocr": {"ocr_preset": "easyocr", "ocr_lang": ["ja", "en"]},
    "rapidocr(iso:ja)": {"ocr_preset": "rapidocr", "ocr_lang": ["iso:ja"]},
    "rapidocr(ch)": {"ocr_preset": "rapidocr", "ocr_lang": ["ch"]},
    "tesseract(jpn)": {"ocr_preset": "tesseract", "ocr_lang": ["jpn", "eng"]},
}


def _md(result_json: dict[str, Any]) -> str:
    return str(result_json["document"].get("md_content") or "")


def cmd_convert(args: argparse.Namespace) -> dict[str, Any]:
    client = DoclingClient(args.url)
    options = {**CONVERT_OPTIONS, **({"ocr_preset": args.ocr_preset} if args.ocr_preset else {})}
    rows: list[dict[str, Any]] = []
    for path in args.files:
        for run in range(args.repeat):
            with PeakSampler() as gpu:
                r = client.convert_file(path, options)
            body = r.json()
            doc_json = body["document"].get("json_content") or {}
            rows.append(
                {
                    "file": path.name,
                    "run": run + 1,
                    "status": r.status,
                    "elapsed_sec": round(r.elapsed_sec, 2),
                    "processing_time": body.get("processing_time"),
                    "pages": len(doc_json.get("pages", {})),
                    "json_bytes": len(json.dumps(doc_json, ensure_ascii=False).encode("utf-8")),
                    "md_bytes": len(_md(body).encode("utf-8")),
                    "pictures": len(doc_json.get("pictures", [])),
                    "tables": len(doc_json.get("tables", [])),
                    "gpu_mem_before_mib": gpu.before,
                    "gpu_mem_peak_mib": gpu.peak,
                    "errors": body.get("errors"),
                }
            )
            print(json.dumps(rows[-1], ensure_ascii=False))
    client.close()
    return {"options": options, "rows": rows}


def cmd_make_scans(args: argparse.Namespace) -> dict[str, Any]:
    made = {}
    for path in args.files:
        dst = args.out / path.name.replace(".pdf", "-scan.pdf")
        made[path.name] = {"scan": str(dst), "pages": make_scanned_pdf(path, dst, dpi=args.dpi)}
        print(path.name, "->", dst)
    return {"dpi": args.dpi, "scans": made}


def cmd_ocr(args: argparse.Namespace) -> dict[str, Any]:
    client = DoclingClient(args.url)
    base = {"to_formats": ["md"], "image_export_mode": "placeholder", "do_table_structure": True}
    results: dict[str, Any] = {"candidates": OCR_CANDIDATES, "files": {}}
    for original in args.originals:
        scan = args.scans / original.name.replace(".pdf", "-scan.pdf")
        # 正解: 元 PDF のテキスト層（OCR なし）を同じパイプラインで Markdown 化したもの
        ref = _md(client.convert_file(original, {**base, "do_ocr": False}).json())
        if args.dump:
            args.dump.mkdir(parents=True, exist_ok=True)
            (args.dump / f"{original.stem}.reference.md").write_text(ref, encoding="utf-8")
        per: dict[str, Any] = {"reference_chars": len(normalize(ref))}
        for name, opts in OCR_CANDIDATES.items():
            times: list[float] = []
            accs: list[float] = []
            statuses: list[str] = []
            body: dict[str, Any] = {}
            for _ in range(args.repeat):
                r = client.convert_file(scan, {**base, "do_ocr": True, "force_ocr": True, **opts})
                body = r.json()
                times.append(r.elapsed_sec)
                accs.append(char_accuracy(ref, _md(body)))
                statuses.append(r.status)
            per[name] = {
                "accuracy": round(statistics.mean(accs), 4),
                "elapsed_sec": round(statistics.median(times), 2),
                "status": statuses,
                "errors": body.get("errors"),
                "chars": len(normalize(_md(body))),
            }
            print(original.name, name, per[name])
            if args.dump:
                (args.dump / f"{original.stem}.{name}.md").write_text(_md(body), encoding="utf-8")
        results["files"][original.name] = per
    client.close()
    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="docling_bench")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("convert", help="1 件ごとの変換時間・GPU メモリ・出力サイズ")
    c.add_argument("--url", required=True)
    c.add_argument("--ocr-preset", default=None)
    c.add_argument("--repeat", type=int, default=1)
    c.add_argument("--out", type=Path, default=Path("results/convert.json"))
    c.add_argument("files", nargs="+", type=Path)

    s = sub.add_parser("make-scans", help="スキャン相当の PDF を作る")
    s.add_argument("--out", type=Path, default=Path("scans"))
    s.add_argument("--dpi", type=int, default=200)
    s.add_argument("files", nargs="+", type=Path)

    o = sub.add_parser("ocr", help="ocr_preset ごとの文字一致率と時間")
    o.add_argument("--url", required=True)
    o.add_argument("--originals", nargs="+", type=Path, required=True)
    o.add_argument("--scans", type=Path, default=Path("scans"))
    o.add_argument("--repeat", type=int, default=2)
    o.add_argument("--dump", type=Path, default=None, help="各エンジンの Markdown を保存する先")
    o.add_argument("--out", type=Path, default=Path("results/ocr.json"))

    args = p.parse_args(argv)
    handler = {"convert": cmd_convert, "make-scans": cmd_make_scans, "ocr": cmd_ocr}[args.cmd]
    result = handler(args)
    out = args.out if args.cmd != "make-scans" else None
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0
