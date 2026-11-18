"use client";

/** 解析の対照（specs/030-parse-inspection）。原件の頁にチャンクの枠を重ね、Docling の抽出文・文脈・埋め込みに送った本文を並べる。
 * - PDF は左に頁の画像（pdf.js）と枠、右にその頁のチャンク。PDF 以外は枠なしで、チャンクの一覧と本文だけ（R11）。
 * - 警告のある頁は札を出し、押すとその頁へ飛ぶ（R12）。 */
import { useEffect, useMemo, useRef, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { isPdf } from "@/lib/file-types";
import { doclingJsonUrl, libraryApi, originalUrl, type DocumentOut } from "@/lib/library/api";
import {
  boxesOnPage,
  boxToRect,
  chunksOnPage,
  firstPageOf,
  warningLabel,
  warningsByPage,
  type ChunkOut,
  type ParseReport,
} from "@/lib/library/inspect";
import { cn } from "@/lib/utils";

export interface InspectPaneProps {
  doc: DocumentOut;
  isAdmin: boolean;
  /** 開いたときに選んでおくチャンク（回答の出典から来たとき。R13） */
  initialChunkId?: string | null;
}

export function InspectPane({ doc, isAdmin, initialChunkId }: InspectPaneProps) {
  const [report, setReport] = useState<ParseReport | null | undefined>(undefined);
  const [chunks, setChunks] = useState<ChunkOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(initialChunkId ?? null);
  const [page, setPage] = useState(1);
  const pdf = isPdf(doc.filename);

  useEffect(() => {
    let alive = true;
    Promise.all([libraryApi.parseReport(doc.id), libraryApi.allChunks(doc.id)]).then(
      ([r, c]) => {
        if (!alive) return;
        setReport(r);
        setChunks(c);
        const first = c.find((x) => x.id === initialChunkId) ?? c[0];
        const p = first ? firstPageOf(first) : null;
        if (p) setPage(p);
        if (!initialChunkId && first) setSelectedId(first.id);
      },
      (e: unknown) => alive && setError(e instanceof Error ? e.message : "読み込めませんでした"),
    );
    return () => {
      alive = false;
    };
  }, [doc.id, initialChunkId]);

  const pages = useMemo(() => {
    if (report && report.pages.length) return report.pages.map((p) => p.page);
    const set = new Set<number>();
    for (const c of chunks ?? []) if (c.page_start != null) set.add(c.page_start);
    return [...set].sort((a, b) => a - b);
  }, [report, chunks]);

  const byPage = useMemo(() => (report ? warningsByPage(report) : new Map()), [report]);
  const selected = chunks?.find((c) => c.id === selectedId) ?? null;
  const onPage = useMemo(() => (chunks ? chunksOnPage(chunks, page) : []), [chunks, page]);
  const sizeOf = (n: number) => report?.pages.find((p) => p.page === n)?.size ?? null;

  const pick = (c: ChunkOut) => {
    setSelectedId(c.id);
    const p = firstPageOf(c);
    if (p && !boxesOnPage(c, page).length) setPage(p);
  };

  if (error) return <div className="p-6 text-footnote text-danger">{error}</div>;
  if (!chunks || report === undefined) return <div className="p-6 text-footnote text-muted">読み込んでいます…</div>;

  return (
    <div className="grid h-full min-h-0 grid-cols-[minmax(0,1fr)_minmax(320px,420px)] max-md:grid-cols-1 max-md:grid-rows-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="flex min-h-0 min-w-0 flex-col border-r-[0.5px] border-divider max-md:border-r-0 max-md:border-b-[0.5px]">
        <PageStrip pages={pages} page={page} onPage={setPage} byPage={byPage} />
        <div className="min-h-0 flex-1 overflow-auto bg-surface-2 p-3">
          {pdf ? (
            <PdfPage
              docId={doc.id}
              page={page}
              pageSize={sizeOf(page)}
              chunks={onPage}
              selectedId={selectedId}
              onPick={pick}
            />
          ) : (
            <div className="mx-auto max-w-[520px] rounded-card border-[0.5px] border-divider bg-bg p-4 text-footnote leading-[1.6] text-muted">
              PDF 以外の形式では、原件の上に枠を重ねません。右のチャンクの一覧と、その本文を確かめてください。
            </div>
          )}
        </div>
      </div>

      <div className="flex min-h-0 min-w-0 flex-col overflow-y-auto">
        <ReportSummary report={report} page={page} byPage={byPage} docId={doc.id} isAdmin={isAdmin} />
        <div className="border-b-[0.5px] border-divider px-3 py-2 text-caption font-medium text-muted">
          {page} ページのチャンク（{onPage.length} 件）
        </div>
        <ul className="m-0 list-none p-0">
          {onPage.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => pick(c)}
                aria-pressed={c.id === selectedId}
                className={cn(
                  "block w-full border-b-[0.5px] border-divider px-3 py-2 text-left text-footnote hover:bg-surface-2",
                  c.id === selectedId && "bg-surface-2",
                )}
              >
                <span className="mr-1.5 rounded-control bg-surface-2 px-1.5 py-px text-mini text-muted">
                  {c.block_type}
                </span>
                <span className="text-muted">{c.heading_path}</span>
                <div className="mt-0.5 line-clamp-2 text-fg">{c.text}</div>
              </button>
            </li>
          ))}
          {onPage.length === 0 && <li className="px-3 py-4 text-footnote text-muted">この頁にチャンクはありません。</li>}
        </ul>
        {selected && <ChunkDetail chunk={selected} />}
      </div>
    </div>
  );
}

function PageStrip({
  pages,
  page,
  onPage,
  byPage,
}: {
  pages: number[];
  page: number;
  onPage: (n: number) => void;
  byPage: Map<number | null, { severity: string; code: string }[]>;
}) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto border-b-[0.5px] border-divider px-3 py-2">
      {pages.map((n) => {
        const ws = byPage.get(n) ?? [];
        const level = ws.some((w) => w.severity === "warn") ? "warn" : ws.length ? "info" : null;
        return (
          <button
            key={n}
            onClick={() => onPage(n)}
            aria-pressed={n === page}
            aria-label={level ? `${n} ページ（警告あり）` : `${n} ページ`}
            title={ws.map((w) => warningLabel(w.code)).join("、") || undefined}
            className={cn(
              "relative min-w-[30px] shrink-0 rounded-control px-2 py-1 text-caption nums",
              n === page ? "bg-accent text-white" : "text-muted hover:bg-surface-2",
            )}
          >
            {n}
            {level && (
              <span
                className={cn(
                  "absolute right-0.5 top-0.5 h-1.5 w-1.5 rounded-full",
                  level === "warn" ? "bg-danger" : "bg-muted-2",
                )}
              />
            )}
          </button>
        );
      })}
    </div>
  );
}

function ReportSummary({
  report,
  page,
  byPage,
  docId,
  isAdmin,
}: {
  report: ParseReport | null;
  page: number;
  byPage: ReturnType<typeof warningsByPage> | Map<number | null, never[]>;
  docId: string;
  isAdmin: boolean;
}) {
  if (!report) {
    return (
      <div className="border-b-[0.5px] border-divider px-3 py-3 text-footnote text-muted">
        この文書には解析の記録がありません（記録を足す前に入れた文書です）。管理者が <code>reparse-report</code> で作り直せます。
      </div>
    );
  }
  const t = report.totals;
  const docling = report.docling as { statuses?: string[]; elapsed_sec?: number; windows?: number } | null;
  const here = [...(byPage.get(page) ?? []), ...(byPage.get(null) ?? [])];
  return (
    <div className="border-b-[0.5px] border-divider px-3 py-3 text-footnote">
      <div className="text-muted">
        {report.parser} · {t.pages} ページ · {t.texts} 文 · {t.tables} 表 · {t.pictures} 図 · {t.chars} 文字 · {t.chunks} チャンク
        {docling?.elapsed_sec != null && ` · 解析 ${docling.elapsed_sec} 秒`}
      </div>
      {docling?.statuses?.some((s) => s !== "success") && (
        <div className="mt-1 text-danger">docling-serve の状態: {docling.statuses.join(", ")}</div>
      )}
      {here.length > 0 ? (
        <ul className="m-0 mt-2 list-none space-y-1 p-0">
          {here.map((w, i) => (
            <li key={i} className={w.severity === "warn" ? "text-danger" : "text-muted"}>
              <span className="mr-1 font-medium">{warningLabel(w.code)}</span>
              {w.message}
            </li>
          ))}
        </ul>
      ) : (
        <div className="mt-1 text-muted">この頁に警告はありません。</div>
      )}
      <div className="mt-2 flex gap-3 text-caption">
        <a className="text-accent underline" href={`/api/v1/documents/${encodeURIComponent(docId)}/rendered`} target="_blank" rel="noopener">
          Markdown
        </a>
        {isAdmin && (
          <a className="text-accent underline" href={doclingJsonUrl(docId)} target="_blank" rel="noopener">
            Docling の JSON
          </a>
        )}
      </div>
    </div>
  );
}

function ChunkDetail({ chunk }: { chunk: ChunkOut }) {
  const blocks: [string, string][] = [
    ["Docling の抽出文（チャンクの文）", chunk.text],
    [`文脈（${chunk.context_source}）`, chunk.context],
    ["埋め込みに送った本文", chunk.body],
  ];
  return (
    <div className="space-y-3 px-3 py-3">
      <div className="text-caption text-muted">
        {chunk.heading_path} · {chunk.block_type} · {chunk.token_len} トークン
        {chunk.page_start != null && ` · ${chunk.page_start}${chunk.page_end && chunk.page_end !== chunk.page_start ? `–${chunk.page_end}` : ""} ページ`}
      </div>
      {blocks.map(([label, body]) => (
        <div key={label}>
          <div className="mb-1 text-caption font-medium text-muted">{label}</div>
          <pre className="m-0 max-h-[240px] overflow-auto whitespace-pre-wrap break-words rounded-control bg-surface-2 p-2 text-footnote leading-[1.6] text-fg">
            {body || "（なし）"}
          </pre>
        </div>
      ))}
    </div>
  );
}

// ── PDF の頁 ───────────────────────────────────────────────────────────

function usePdf(docId: string) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    let destroy: (() => Promise<void>) | null = null;
    (async () => {
      const pdfjs = await import("pdfjs-dist");
      pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();
      const task = pdfjs.getDocument({
        url: originalUrl(docId),
        cMapUrl: "/pdfjs/cmaps/",
        cMapPacked: true,
        standardFontDataUrl: "/pdfjs/standard_fonts/",
        wasmUrl: "/pdfjs/wasm/",
      });
      destroy = () => task.destroy();
      const loaded = await task.promise;
      if (alive) setPdf(loaded);
    })().catch((e: unknown) => alive && setError(e instanceof Error ? e.message : "PDF を読めませんでした"));
    return () => {
      alive = false;
      void destroy?.();
    };
  }, [docId]);
  return { pdf, error };
}

function PdfPage({
  docId,
  page,
  pageSize,
  chunks,
  selectedId,
  onPick,
}: {
  docId: string;
  page: number;
  pageSize: number[] | null;
  chunks: ChunkOut[];
  selectedId: string | null;
  onPick: (c: ChunkOut) => void;
}) {
  const { pdf, error } = usePdf(docId);
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(0);
  // 頁の大きさ（pt）。枠の座標は PDF の座標なので、PDF 自身の大きさを使う（記録の値は PDF を開く前の代わり）
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!pdf || !canvasRef.current || width <= 0) return;
    let cancelled = false;
    let task: { cancel: () => void; promise: Promise<unknown> } | null = null;
    (async () => {
      const p = await pdf.getPage(Math.min(Math.max(page, 1), pdf.numPages));
      const base = p.getViewport({ scale: 1 });
      if (cancelled) return;
      setNatural({ w: base.width, h: base.height });
      const scale = width / base.width;
      const dpr = window.devicePixelRatio || 1;
      const viewport = p.getViewport({ scale: scale * dpr });
      const canvas = canvasRef.current!;
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${base.height * scale}px`;
      task = p.render({ canvas, viewport });
      await task.promise;
    })().catch(() => {});
    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [pdf, page, width]);

  const h = natural?.h ?? pageSize?.[1] ?? 0;
  const scale = natural && width ? width / natural.w : 0;
  return (
    <div ref={wrapRef} className="relative mx-auto w-full max-w-[860px]">
      {error && <div className="text-footnote text-danger">{error}</div>}
      <canvas ref={canvasRef} className="block rounded-control bg-white shadow-sm" />
      {scale > 0 &&
        chunks.flatMap((c) =>
          boxesOnPage(c, page).map((b, i) => {
            const r = boxToRect(b, h, scale);
            const on = c.id === selectedId;
            return (
              <button
                key={`${c.id}-${i}`}
                onClick={() => onPick(c)}
                aria-label={c.text.slice(0, 40)}
                title={c.text.slice(0, 80)}
                className={cn(
                  "absolute rounded-[2px] border",
                  on ? "z-10 border-accent bg-accent/20" : "border-accent/40 hover:bg-accent/10",
                )}
                style={{ left: r.left, top: r.top, width: r.width, height: r.height }}
              />
            );
          }),
        )}
    </div>
  );
}
