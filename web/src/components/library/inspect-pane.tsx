"use client";

/** 解析の確認（specs/030-parse-inspection）。原件の頁にチャンクの枠を重ね、チャンクの文・文脈・埋め込みに送った本文を確かめる。
 * - PDF は左に頁（pdf.js）と枠、右に解析の記録とその頁のチャンク。枠とチャンクは互いに選び合う（R9・R10）。
 * - PDF 以外は枠を重ねず、整形表示と同じ幅の 1 列で記録とチャンクを並べる（R11）。
 * - 警告は記録の欄にまとめ、押すとその頁へ飛ぶ。頁の移動は ← → でもできる（R12）。
 * - 枠と一覧の行はホバー・フォーカスで互いに光る（回答の印と根拠カードと同じ部品。ui/link-marks）。
 * - 「読み順」を入れると枠にチャンクの番号（Docling が読んだ順）を出す。段組みの読み違いを見つけるため。普段は原件を隠さないよう出さない。 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { Badge } from "@/components/ui/badge";
import { Card, cardClass } from "@/components/ui/card";
import { linkHandlers, linkMarks } from "@/components/ui/link-marks";
import { Button, IconButton } from "@/components/ui/button";
import { Icon } from "@/components/icons";
import { ListSkeleton, Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/chat/api";
import { isPdf } from "@/lib/file-types";
import { doclingJsonUrl, libraryApi, originalUrl, type DocumentOut } from "@/lib/library/api";
import {
  adjacentPage,
  BLOCK_LABEL,
  boxesOnPage,
  boxToRect,
  chunksOnPage,
  CONTEXT_SOURCE_LABEL,
  firstPageOf,
  nextWarningPage,
  warningLabel,
  type ChunkOut,
  type ParseReport,
  type ParseWarning,
} from "@/lib/library/inspect";
import { headingCrumb, pageLabel } from "@/lib/library/view";
import { cn } from "@/lib/utils";
import { t } from "@/i18n";
import { interpolate } from "@/i18n/interpolate";

export interface InspectPaneProps {
  doc: DocumentOut;
  isAdmin: boolean;
  /** 開いたときに選んでおく章（回答の出典から来たとき。その章の最初のチャンクを選ぶ。R13） */
  initialSectionId?: string | null;
}

export function InspectPane({ doc, isAdmin, initialSectionId }: InspectPaneProps) {
  const [report, setReport] = useState<ParseReport | null | undefined>(undefined);
  const [chunks, setChunks] = useState<ChunkOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [showOrder, setShowOrder] = useState(false);
  // 一覧から選んだら頁の枠へ、枠から選んだら一覧の行へ、見える位置まで送る
  const [reveal, setReveal] = useState<{ target: "box" | "row"; n: number }>({ target: "box", n: 0 });
  const pdf = isPdf(doc.filename);

  useEffect(() => {
    let alive = true;
    Promise.all([libraryApi.parseReport(doc.id), libraryApi.allChunks(doc.id)]).then(
      ([r, c]) => {
        if (!alive) return;
        setReport(r);
        setChunks(c);
        const first = (initialSectionId ? c.find((x) => x.section_id === initialSectionId) : undefined) ?? c[0];
        const p = first ? firstPageOf(first) : null;
        if (p) setPage(p);
        if (first) {
          setSelectedId(first.id);
          setReveal((x) => ({ target: "box", n: x.n + 1 }));
        }
      },
      (e: unknown) => alive && setError(e instanceof ApiError ? e.message : t.inspect.reportLoadFailed),
    );
    return () => {
      alive = false;
    };
  }, [doc.id, initialSectionId, attempt]);

  const pages = useMemo(() => {
    if (report && report.pages.length) return report.pages.map((p) => p.page);
    const set = new Set<number>();
    for (const c of chunks ?? []) if (c.page_start != null) set.add(c.page_start);
    return [...set].sort((a, b) => a - b);
  }, [report, chunks]);
  // 頁の無い形式（docx など）は、頁で絞らず全チャンクを出す
  const paged = pages.length > 0;
  const onPage = useMemo(() => (chunks ? (paged ? chunksOnPage(chunks, page) : chunks) : []), [chunks, page, paged]);
  const pageSize = report?.pages.find((p) => p.page === page)?.size ?? null;

  const goto = useCallback((n: number | null) => n != null && setPage(n), []);

  // ← → で頁を送る（入力欄・修飾キーつきは除く）
  useEffect(() => {
    if (!paged) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
      if (e.key === "ArrowLeft") goto(adjacentPage(pages, page, -1));
      else if (e.key === "ArrowRight") goto(adjacentPage(pages, page, 1));
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [paged, pages, page, goto]);

  const pick = (c: ChunkOut, from: "list" | "box") => {
    setSelectedId(c.id);
    if (from === "list" && paged && !boxesOnPage(c, page).length) goto(firstPageOf(c));
    setReveal((x) => ({ target: from === "list" ? "box" : "row", n: x.n + 1 }));
  };

  if (error) {
    return (
      <div className="grid h-full place-items-center p-8 text-center">
        <div className="text-footnote text-danger">
          {error}
          <button
            onClick={() => {
              setError(null);
              setAttempt((n) => n + 1);
            }}
            className="ml-2 underline"
          >
            {t.common.tryAgain}
          </button>
        </div>
      </div>
    );
  }

  const loading = !chunks || report === undefined;
  const summary = loading ? (
    <Card className="grid gap-2 p-3.5">
      <Skeleton className="h-3 w-[40%]" />
      <Skeleton className="h-2.5 w-[70%]" />
    </Card>
  ) : (
    <ReportSummary report={report} page={paged ? page : null} onGoto={goto} docId={doc.id} isAdmin={isAdmin} />
  );
  const list = loading ? (
    <ListSkeleton rows={5} />
  ) : (
    <ChunkList
      chunks={onPage}
      page={paged ? page : null}
      selectedId={selectedId}
      revealRow={reveal.target === "row" ? reveal.n : 0}
      onPick={(c) => pick(c, "list")}
      withBoxes={pdf}
    />
  );
  const nav = paged && !loading && (
    <PageNav pages={pages} page={page} onGoto={goto} nextWarning={nextWarningPage(report ?? null, page)} />
  );

  if (!pdf) {
    return (
      <div data-inspect className="h-full overflow-y-auto">
        <div className="mx-auto flex max-w-[820px] flex-col gap-4 px-8 pb-24 pt-6 max-md:px-4">
          {summary}
          <p className="m-0 text-caption text-muted">
            {t.inspect.noOverlay}
          </p>
          {nav && <div className="flex items-center">{nav}</div>}
          {list}
        </div>
      </div>
    );
  }

  return (
    <div data-inspect className="grid h-full min-h-0 grid-cols-[minmax(0,1fr)_400px] max-lg:grid-cols-[minmax(0,1fr)_340px] max-md:grid-cols-1 max-md:grid-rows-[minmax(0,55fr)_minmax(0,45fr)]">
      <div className="flex min-h-0 min-w-0 flex-col border-r-[0.5px] border-divider max-md:border-b-[0.5px] max-md:border-r-0">
        <div className="flex h-11 shrink-0 items-center gap-2 border-b-[0.5px] border-divider px-3">
          {nav}
          <Button
            variant="ghost"
            size="sm"
            aria-pressed={showOrder}
            onClick={() => setShowOrder((x) => !x)}
            title={t.inspect.readingOrderHint}
            className={cn("ml-auto", showOrder ? "bg-divider text-fg" : "text-muted")}
          >
            <Icon name="layers" size={12} />
            {t.inspect.readingOrder}
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto bg-bg-2 px-6 py-5 max-md:px-3 max-md:py-3">
          <PdfPage
            docId={doc.id}
            page={page}
            pageSize={pageSize}
            chunks={onPage}
            selectedId={selectedId}
            showOrder={showOrder}
            revealBox={reveal.target === "box" ? reveal.n : 0}
            onPick={(c) => pick(c, "box")}
          />
        </div>
      </div>
      <div className="flex min-h-0 min-w-0 flex-col gap-3 overflow-y-auto p-3">
        {summary}
        {list}
      </div>
    </div>
  );
}

// ── 頁の移動 ───────────────────────────────────────────────────────────

function PageNav({
  pages,
  page,
  onGoto,
  nextWarning,
}: {
  pages: number[];
  page: number;
  onGoto: (n: number | null) => void;
  nextWarning: number | null;
}) {
  const prev = adjacentPage(pages, page, -1);
  const next = adjacentPage(pages, page, 1);
  return (
    <>
      <div className="inline-flex items-center gap-0.5">
        <IconButton label={t.inspect.prevPage} icon="chevronLeft" disabled={prev == null} onClick={() => onGoto(prev)} />
        <span className="min-w-[64px] text-center font-mono text-footnote text-fg-2" aria-live="polite">
          {page} / {pages.length}
        </span>
        <IconButton label={t.inspect.nextPage} icon="chevronRight" disabled={next == null} onClick={() => onGoto(next)} />
      </div>
      {nextWarning != null && nextWarning !== page && (
        <Button variant="ghost" size="sm" onClick={() => onGoto(nextWarning)} className="text-danger">
          <Icon name="alert" size={12} />
          {interpolate(t.inspect.nextWarningPage, { nextWarning })}
        </Button>
      )}
    </>
  );
}

// ── 解析の記録 ─────────────────────────────────────────────────────────

function ReportSummary({
  report,
  page,
  onGoto,
  docId,
  isAdmin,
}: {
  report: ParseReport | null;
  /** 頁のある形式なら今の頁（その頁の警告を強調する） */
  page: number | null;
  onGoto: (n: number | null) => void;
  docId: string;
  isAdmin: boolean;
}) {
  const links = (
    <div className="flex items-center gap-0.5">
      <Button asChild variant="ghost" size="sm" className="h-6 px-1.5 text-caption text-muted">
        <a href={`/api/v1/documents/${encodeURIComponent(docId)}/rendered`} target="_blank" rel="noopener">
          Markdown
          <Icon name="external" size={11} />
        </a>
      </Button>
      {isAdmin && (
        <Button asChild variant="ghost" size="sm" className="h-6 px-1.5 text-caption text-muted">
          <a href={doclingJsonUrl(docId)} target="_blank" rel="noopener" title={t.inspect.rawJson}>
            Docling JSON
            <Icon name="external" size={11} />
          </a>
        </Button>
      )}
    </div>
  );

  if (!report) {
    return (
      <section className={cn(cardClass(), "p-3.5")}>
        <div className="flex items-center justify-between gap-2">
          <h3 className="m-0 text-caption font-medium text-muted">{t.inspect.reportTitle}</h3>
          {links}
        </div>
        <p className="m-0 mt-1.5 text-footnote leading-[1.6] text-muted">
          {t.inspect.noReportBefore}
          {isAdmin && (
            <>
              {" "}
              <code className="rounded bg-code-bg px-1 font-mono text-caption">python -m arag.cli reparse-report</code> {t.inspect.noReportAfter}
            </>
          )}
        </p>
      </section>
    );
  }

  const totals = report.totals;
  const docling = report.docling as { statuses?: string[]; elapsed_sec?: number } | null;
  const degraded = docling?.statuses?.filter((s) => s !== "success") ?? [];
  // warn を先に、同じ重さの中は頁の順
  const warnings = [...report.warnings].sort(
    (a, b) => Number(b.severity === "warn") - Number(a.severity === "warn") || (a.page ?? 0) - (b.page ?? 0),
  );
  const warnCount = warnings.filter((w) => w.severity === "warn").length;
  const stats: [string, number][] = [
    [t.inspect.statPages, totals.pages ?? 0],
    [t.inspect.statTexts, totals.texts ?? 0],
    [t.inspect.statTables, totals.tables ?? 0],
    [t.inspect.statPictures, totals.pictures ?? 0],
    [t.inspect.statChunks, totals.chunks ?? 0],
  ];

  return (
    <section className={cardClass()}>
      <div className="flex items-center justify-between gap-2 px-3.5 pt-2.5">
        <h3 className="m-0 flex items-center gap-1.5 text-caption font-medium text-muted">
          {t.inspect.reportTitle}
          {warnCount > 0 ? <Badge tone="danger">{interpolate(t.inspect.warnCount, { warnCount })}</Badge> : <Badge>{t.inspect.noWarnings}</Badge>}
        </h3>
        {links}
      </div>
      <dl className="m-0 grid grid-cols-5 gap-1 px-3.5 pb-2 pt-1.5">
        {stats.map(([label, n]) => (
          <div key={label} className="min-w-0">
            <dt className="text-mini text-muted-2">{label}</dt>
            <dd className="m-0 font-mono text-footnote text-fg">{n.toLocaleString("ja-JP")}</dd>
          </div>
        ))}
      </dl>
      <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 border-t-[0.5px] border-divider px-3.5 py-2 text-caption text-muted">
        <span className="font-mono">{report.parser}</span>
        {docling?.elapsed_sec != null && <span>{interpolate(t.inspect.elapsed, { elapsed_sec: docling.elapsed_sec })}</span>}
        <span>{interpolate(t.inspect.chars, { n: (totals.chars ?? 0).toLocaleString("ja-JP") })}</span>
        {degraded.length > 0 && <Badge tone="danger">docling-serve: {[...new Set(degraded)].join(", ")}</Badge>}
      </div>
      {warnings.length > 0 && (
        <ul className="m-0 max-h-[180px] list-none overflow-y-auto border-t-[0.5px] border-divider p-1">
          {warnings.map((w, i) => (
            <WarningRow key={i} warning={w} current={page != null && w.page === page} onGoto={onGoto} />
          ))}
        </ul>
      )}
    </section>
  );
}

function WarningRow({
  warning: w,
  current,
  onGoto,
}: {
  warning: ParseWarning;
  current: boolean;
  onGoto: (n: number | null) => void;
}) {
  const body = (
    <>
      <Badge tone={w.severity === "warn" ? "danger" : "neutral"}>{warningLabel(w.code)}</Badge>
      <span className="min-w-0 flex-1 text-caption leading-[1.5] text-fg-2">{w.message}</span>
      {w.page != null && <span className="shrink-0 font-mono text-mini text-muted-2">p.{w.page}</span>}
    </>
  );
  const cls = cn("flex w-full items-start gap-2 rounded-control px-2.5 py-1.5 text-left", current && "bg-divider");
  return (
    <li>
      {w.page != null ? (
        <button onClick={() => onGoto(w.page)} className={cn(cls, "hover:bg-divider")}>
          {body}
        </button>
      ) : (
        <div className={cls}>{body}</div>
      )}
    </li>
  );
}

// ── チャンクの一覧 ─────────────────────────────────────────────────────

function ChunkList({
  chunks,
  page,
  selectedId,
  revealRow,
  onPick,
  withBoxes,
}: {
  chunks: ChunkOut[];
  page: number | null;
  selectedId: string | null;
  /** 0 以外に変わったら選んだ行を見える位置まで送る */
  revealRow: number;
  onPick: (c: ChunkOut) => void;
  /** 原本に枠を重ねる形式（PDF）か。位置の無いチャンクにその旨を出す */
  withBoxes: boolean;
}) {
  const ref = useRef<HTMLUListElement>(null);
  useEffect(() => {
    if (!revealRow) return;
    ref.current?.querySelector<HTMLElement>("[data-selected='true']")?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [revealRow]);

  return (
    <section className="flex min-w-0 flex-col gap-1.5">
      <h3 className="m-0 flex items-center gap-1.5 px-1 text-caption font-medium text-muted">
        {page != null ? interpolate(t.inspect.chunksOnPage, { page }) : t.inspect.statChunks}
        <Badge>{chunks.length}</Badge>
      </h3>
      {chunks.length === 0 ? (
        <p className="m-0 rounded-card border-[0.5px] border-dashed border-divider-strong px-3.5 py-4 text-footnote text-muted">
          {page != null ? t.inspect.noChunksOnPage : t.inspect.noChunks}
        </p>
      ) : (
        <ul ref={ref} className="m-0 flex list-none flex-col gap-2 p-0">
          {chunks.map((c) => (
            <ChunkRow
              key={c.id}
              chunk={c}
              selected={c.id === selectedId}
              onPick={() => onPick(c)}
              noBox={withBoxes && c.boxes.length === 0}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

/** 枠と行を互いに光らせる（同じ番号の印・枠・行）。 */
function chunkLink(id: string) {
  return linkHandlers((from, on) => linkMarks(from, "[data-inspect]", `[data-chunk="${id}"]`, on));
}

/** チャンクの番号（文書の中の順。枠と行で同じ） */
const chunkNo = (c: ChunkOut) => c.ordinal + 1;

function ChunkRow({
  chunk: c,
  selected,
  onPick,
  noBox,
}: {
  chunk: ChunkOut;
  selected: boolean;
  onPick: () => void;
  /** 原本の上の位置を持たない（枠を描けない） */
  noBox: boolean;
}) {
  const pages = pageLabel(c.page_start, c.page_end);
  return (
    <li
      data-chunk={c.id}
      data-selected={selected}
      {...chunkLink(c.id)}
      className={cn(cardClass({ tone: "linked" }), "min-w-0", selected && "border-accent")}
    >
      <button onClick={onPick} aria-expanded={selected} className="block w-full rounded-card px-2.5 py-2 text-left outline-none">
        <span className="flex min-w-0 items-center gap-1.5">
          <span className="nums shrink-0 font-mono text-mini text-muted-2">#{chunkNo(c)}</span>
          <Badge>{BLOCK_LABEL[c.block_type] ?? c.block_type}</Badge>
          <span className="min-w-0 flex-1 truncate text-mini text-muted" title={headingCrumb(c.heading_path)}>
            {headingCrumb(c.heading_path) || t.viewer.untitledSection}
          </span>
          {noBox && (
            <span className="shrink-0 text-mini text-muted-2" title={t.inspect.noBoxHint}>
              {t.inspect.noBox}
            </span>
          )}
          {pages && <span className="nums shrink-0 font-mono text-mini text-muted-2">{pages}</span>}
        </span>
        {!selected && <span className="mt-1.5 line-clamp-3 text-caption leading-[1.6] text-fg-2 [overflow-wrap:anywhere]">{c.text}</span>}
      </button>
      {selected && <ChunkDetail chunk={c} />}
    </li>
  );
}

function ChunkDetail({ chunk: c }: { chunk: ChunkOut }) {
  return (
    <div className="grid gap-2.5 px-2.5 pb-2.5">
      <Field label={t.inspect.chunkText} aside={interpolate(t.inspect.tokens, { token_len: c.token_len })}>
        {c.text}
      </Field>
      <Field label={t.inspect.context} aside={CONTEXT_SOURCE_LABEL[c.context_source] ?? c.context_source}>
        {c.context || t.inspect.none}
      </Field>
      <details className="group">
        <summary className="flex cursor-pointer list-none items-center gap-1 text-caption font-medium text-muted hover:text-fg [&::-webkit-details-marker]:hidden">
          <Icon name="chevronRight" size={11} className="transition-transform group-open:rotate-90" />
          {t.inspect.embeddedText}
        </summary>
        <pre className="m-0 mt-1 max-h-[220px] overflow-auto whitespace-pre-wrap break-words rounded-control bg-bg-2 p-2 font-sans text-footnote leading-[1.6] text-fg-2">
          {c.body}
        </pre>
      </details>
    </div>
  );
}

function Field({ label, aside, children }: { label: string; aside?: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2 text-caption">
        <span className="font-medium text-muted">{label}</span>
        {aside && <span className="text-mini text-muted-2">{aside}</span>}
      </div>
      <div className="max-h-[260px] select-text overflow-auto whitespace-pre-wrap break-words rounded-control bg-bg-2 p-2 text-footnote leading-[1.6] text-fg">
        {children}
      </div>
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
    })().catch(() => alive && setError(t.inspect.pdfFailed));
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
  showOrder,
  revealBox,
  onPick,
}: {
  docId: string;
  page: number;
  /** 記録にある頁の大きさ（PDF を開くまでの骨組みの縦横比に使う） */
  pageSize: number[] | null;
  chunks: ChunkOut[];
  selectedId: string | null;
  /** 枠にチャンクの番号（読み順）を出す */
  showOrder: boolean;
  /** 0 以外に変わったら選んだ枠を見える位置まで送る */
  revealBox: number;
  onPick: (c: ChunkOut) => void;
}) {
  const { pdf, error } = usePdf(docId);
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(0);
  // 描き終えた頁とその大きさ（pt）。枠の座標は PDF の座標なので、PDF 自身の大きさで直す
  const [drawn, setDrawn] = useState<{ page: number; w: number; h: number } | null>(null);

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
      if (cancelled) return;
      const base = p.getViewport({ scale: 1 });
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
      if (!cancelled) setDrawn({ page, w: base.width, h: base.height });
    })().catch(() => {});
    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [pdf, page, width]);

  const ready = drawn?.page === page && width > 0;
  const scale = ready ? width / drawn.w : 0;

  useEffect(() => {
    if (!revealBox || !ready) return;
    wrapRef.current
      ?.querySelector<HTMLElement>("[data-selected='true']")
      ?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [revealBox, ready, page]);

  if (error) {
    return <div className="mx-auto max-w-[520px] py-10 text-center text-footnote text-muted">{error}</div>;
  }
  const ratio = pageSize && pageSize[0] && pageSize[1] ? pageSize[0] / pageSize[1] : 1 / Math.SQRT2;
  return (
    <div ref={wrapRef} className="relative mx-auto w-full max-w-[860px]">
      {!ready && <div aria-hidden style={{ aspectRatio: ratio }} className="w-full animate-soft-pulse rounded-[4px] bg-fg/10 motion-reduce:animate-none" />}
      <canvas
        ref={canvasRef}
        aria-label={interpolate(t.inspect.pageAria, { page })}
        className={cn("block rounded-[4px] bg-white shadow-e2", !ready && "absolute inset-x-0 top-0 opacity-0")}
      />
      {ready &&
        chunks.flatMap((c) =>
          boxesOnPage(c, page).map((b, i) => {
            const r = boxToRect(b, drawn.h, scale);
            const on = c.id === selectedId;
            return (
              <button
                key={`${c.id}-${i}`}
                data-chunk={c.id}
                data-selected={on && i === 0}
                onClick={() => onPick(c)}
                {...chunkLink(c.id)}
                aria-label={interpolate(t.inspect.boxTitle, { c: chunkNo(c), v: c.text.slice(0, 40) })}
                aria-pressed={on}
                className={cn(
                  "absolute rounded-[3px] border outline-none transition-[background-color,border-color,box-shadow] duration-(--duration-fast) focus-visible:ring-2 focus-visible:ring-accent/50",
                  on
                    ? "z-10 border-accent bg-accent/10 ring-2 ring-accent/25"
                    : "border-fg/15 data-[on]:z-10 data-[on]:border-accent data-[on]:bg-accent-soft/60",
                )}
                style={{ left: r.left - 2, top: r.top - 2, width: r.width + 4, height: r.height + 4 }}
              >
                {showOrder && i === 0 && (
                  <span
                    aria-hidden
                    className="nums pointer-events-none absolute -left-px -top-[15px] rounded-[3px] bg-fg/80 px-1 font-mono text-[9.5px] leading-[14px] text-bg"
                  >
                    #{chunkNo(c)}
                  </span>
                )}
              </button>
            );
          }),
        )}
    </div>
  );
}
