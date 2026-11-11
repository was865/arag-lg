"use client";

/** 文書ビューア（specs/007-document-viewer）。ライブラリの上に重ねて、解析結果（章ごとの整形表示・目次）と原本を読む。
 * - 章は 50 件ずつ読み、末尾が見えたら続きを読む（R4）。目次から未読の章へ飛ぶときはそこまで読み足す。
 * - 「この文書に質問」で検索範囲をこの文書に絞ってチャットへ戻る（R9）。 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/icons";
import { OriginalPreview } from "@/components/documents/original-preview";
import { RenderedSectionBody } from "@/components/sources/rendered-section-body";
import { ApiError } from "@/lib/chat/api";
import { getFileMeta, getTextPreviewKind } from "@/lib/file-types";
import { libraryApi, originalUrl, type DocumentOut, type OutlineSection, type SectionOut } from "@/lib/library/api";
import { docStatus, formatBytes } from "@/lib/library/view";
import { activeSectionId, outlineIndent, pipeTablesToHtml, resolveAssets } from "@/lib/library/viewer";
import { cn } from "@/lib/utils";

const PAGE = 50;
const TEXT_LIMIT = 1024 * 1024;

type Tab = "parsed" | "original";

export interface DocumentViewerProps {
  doc: DocumentOut;
  kbName: string;
  onClose: () => void;
  onAsk: (doc: DocumentOut) => void;
}

export function DocumentViewer({ doc: initial, kbName, onClose, onAsk }: DocumentViewerProps) {
  const [doc, setDoc] = useState(initial);
  const ready = doc.status === "ready";
  const [tab, setTab] = useState<Tab>(ready ? "parsed" : "original");
  const [outlineOpen, setOutlineOpen] = useState(false);
  const meta = getFileMeta(doc.filename);
  const st = docStatus(doc.status);

  // 状態・件数は開いた時点の最新を取り直す
  useEffect(() => {
    let alive = true;
    libraryApi.document(initial.id).then(
      (d) => alive && setDoc(d),
      () => {},
    );
    return () => {
      alive = false;
    };
  }, [initial.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !e.defaultPrevented) onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const facts = [
    kbName,
    st.label,
    doc.page_count ? `${doc.page_count} ページ` : null,
    ready ? `${doc.chunk_count} チャンク` : null,
    formatBytes(doc.size),
  ].filter(Boolean);

  return (
    <div
      role="dialog"
      // eslint-disable-next-line no-restricted-syntax -- 文書ビューアは画面全体を置き換える独立したビューで、ダイアログの見た目に収まらない
      aria-modal="true"
      aria-label={doc.filename}
      className="fixed inset-0 z-[200] grid animate-overlay-in grid-cols-[minmax(0,1fr)] grid-rows-[auto_auto_minmax(0,1fr)] bg-bg"
    >
      <header className="flex h-[56px] items-center gap-2.5 border-b-[0.5px] border-divider px-4 max-md:h-[52px] max-md:gap-1.5 max-md:px-2">
        <button
          onClick={onClose}
          aria-label="閉じる"
          className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-lg text-fg hover:bg-divider"
        >
          <Icon name="chevronLeft" size={16} />
        </button>
        <span
          className="grid h-8 w-8 shrink-0 place-items-center rounded-lg max-md:hidden"
          style={{ color: meta.color, background: `color-mix(in srgb, ${meta.color} 12%, transparent)` }}
        >
          <Icon name={meta.iconName} size={15} />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="m-0 truncate text-[14px] font-semibold text-fg" title={doc.filename}>
            {doc.filename}
          </h2>
          <div className="truncate text-[11px] text-muted">{facts.join(" · ")}</div>
        </div>
        <a
          href={originalUrl(doc.id)}
          target="_blank"
          rel="noopener"
          aria-label="原本を新しいタブで開く"
          title="原本を新しいタブで開く"
          className="grid h-[32px] w-[32px] shrink-0 place-items-center rounded-lg text-muted hover:bg-divider hover:text-fg"
        >
          <Icon name="external" size={14} />
        </a>
        <a
          href={originalUrl(doc.id)}
          download={doc.filename}
          aria-label="ダウンロード"
          title="ダウンロード"
          className="grid h-[32px] w-[32px] shrink-0 place-items-center rounded-lg text-muted hover:bg-divider hover:text-fg"
        >
          <Icon name="download" size={14} />
        </a>
        <Button variant="primary" size="md"
          disabled={!ready}
          onClick={() => onAsk(doc)}
          title={ready ? undefined : "解析が終わると質問できます"}
          className="max-md:px-2.5"
        >
          <Icon name="chat" size={13} />
          <span className="max-md:hidden">この文書に質問</span>
          <span className="hidden max-md:inline">質問</span>
        </Button>
      </header>

      <div className="flex items-center gap-1 border-b-[0.5px] border-divider px-4 max-md:px-2">
        {ready && (
          <button
            onClick={() => setOutlineOpen((x) => !x)}
            aria-label="目次"
            aria-expanded={outlineOpen}
            className={cn(
              "mr-1 hidden h-[30px] w-[30px] place-items-center rounded-md text-muted hover:bg-divider hover:text-fg",
              tab === "parsed" && "max-md:grid",
            )}
          >
            <Icon name="menu" size={14} />
          </button>
        )}
        {(
          [
            ["parsed", "整形表示"],
            ["original", "原本"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            aria-pressed={tab === key}
            className={cn(
              "-mb-px border-b-2 px-3 py-2.5 text-[12.5px] font-medium",
              tab === key ? "border-accent text-fg" : "border-transparent text-muted hover:text-fg",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="min-h-0">
        {tab === "original" ? (
          <OriginalPane doc={doc} onShowParsed={ready ? () => setTab("parsed") : undefined} />
        ) : ready ? (
          <ParsedPane docId={doc.id} outlineOpen={outlineOpen} onCloseOutline={() => setOutlineOpen(false)} />
        ) : (
          <NotReady status={doc.status} onShowOriginal={() => setTab("original")} />
        )}
      </div>
    </div>
  );
}

function NotReady({ status, onShowOriginal }: { status: string; onShowOriginal: () => void }) {
  const failed = status === "error" || status === "cancelled";
  return (
    <div className="grid h-full place-items-center p-8 text-center">
      <div className="max-w-[360px]">
        <div className="mb-1.5 text-[13.5px] font-semibold text-fg">
          {failed ? "この文書は解析できませんでした" : "解析しています"}
        </div>
        <div className="mb-4 text-[12px] leading-[1.6] text-muted">
          {failed
            ? "ライブラリの行のメニューから解析し直せます。原本はそのまま読めます。"
            : "解析が終わると、章ごとの整形表示と目次がここに出ます。"}
        </div>
        <button
          onClick={onShowOriginal}
          className="inline-flex items-center rounded-lg border-[0.5px] border-divider-strong bg-surface px-3 py-1.5 text-[12px] font-medium text-fg hover:bg-surface-2"
        >
          原本を見る
        </button>
      </div>
    </div>
  );
}

// ── 整形表示 ─────────────────────────────────────────────────────────────

function ParsedPane({
  docId,
  outlineOpen,
  onCloseOutline,
}: {
  docId: string;
  outlineOpen: boolean;
  onCloseOutline: () => void;
}) {
  const [outline, setOutline] = useState<OutlineSection[] | null>(null);
  const [sections, setSections] = useState<SectionOut[]>([]);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const loading = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const loadedRef = useRef<SectionOut[]>([]);
  const doneRef = useRef(false);

  /** 少なくとも count 件まで読む（目次から飛ぶとき・末尾が見えたとき）。 */
  const loadUntil = useCallback(
    async (count: number) => {
      if (loading.current) return;
      loading.current = true;
      try {
        while (!doneRef.current && loadedRef.current.length < count) {
          const offset = loadedRef.current.length;
          const limit = Math.min(100, Math.max(PAGE, count - offset));
          const page = await libraryApi.sections(docId, offset, limit);
          loadedRef.current = [...loadedRef.current, ...page];
          if (page.length < limit) doneRef.current = true;
          setSections(loadedRef.current);
          setDone(doneRef.current);
        }
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "本文を読み込めませんでした");
      } finally {
        loading.current = false;
      }
    },
    [docId],
  );

  useEffect(() => {
    let alive = true;
    libraryApi.outline(docId).then(
      (o) => alive && setOutline(o),
      () => alive && setOutline([]),
    );
    void loadUntil(PAGE);
    return () => {
      alive = false;
    };
  }, [docId, loadUntil]);

  // 末尾が見えたら続きを読む
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el || done) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((x) => x.isIntersecting)) void loadUntil(loadedRef.current.length + PAGE);
      },
      { root: scrollRef.current, rootMargin: "600px 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [done, loadUntil, sections.length]);

  const onScroll = () => {
    const root = scrollRef.current;
    if (!root) return;
    const tops = Array.from(root.querySelectorAll<HTMLElement>("[data-section-id]")).map((el) => ({
      id: el.dataset.sectionId!,
      top: el.offsetTop,
    }));
    setActive(activeSectionId(tops, root.scrollTop));
  };
  useEffect(onScroll, [sections.length]);

  const jump = async (index: number, id: string) => {
    onCloseOutline();
    if (loadedRef.current.length <= index) await loadUntil(index + 1);
    requestAnimationFrame(() => {
      const el = scrollRef.current?.querySelector<HTMLElement>(`[data-section-id="${id}"]`);
      if (el && scrollRef.current) scrollRef.current.scrollTo({ top: el.offsetTop - 12, behavior: "smooth" });
    });
  };

  const indents = outline ? outlineIndent(outline) : [];
  const toc = (
    <nav aria-label="目次" className="flex flex-col gap-px p-2">
      <div className="px-2 pb-1.5 pt-1 text-[10px] font-bold uppercase tracking-[0.07em] text-muted-2">目次</div>
      {outline === null ? (
        <div className="px-2 py-1 text-[12px] text-muted">読み込み中…</div>
      ) : outline.length === 0 ? (
        <div className="px-2 py-1 text-[12px] text-muted">見出しはありません</div>
      ) : (
        outline.map((s, i) => (
          <button
            key={s.id}
            onClick={() => void jump(i, s.id)}
            aria-current={active === s.id ? "location" : undefined}
            style={{ paddingLeft: 8 + indents[i]! * 12 }}
            className={cn(
              "flex w-full items-baseline gap-2 rounded-md py-1.5 pr-2 text-left text-[12px] leading-[1.45]",
              active === s.id ? "bg-accent-soft font-medium text-fg" : "text-fg-2 hover:bg-divider",
            )}
          >
            <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">{headingOf(s.heading_path) || "（見出しなし）"}</span>
            {s.page_start != null && <span className="shrink-0 font-mono text-[10.5px] text-muted-2">p.{s.page_start}</span>}
          </button>
        ))
      )}
    </nav>
  );

  return (
    <div className="relative grid h-full grid-cols-[260px_minmax(0,1fr)] max-md:grid-cols-[minmax(0,1fr)]">
      <aside className="min-h-0 overflow-y-auto border-r-[0.5px] border-divider max-md:hidden">{toc}</aside>
      {outlineOpen && (
        <div className="absolute inset-0 z-[5] hidden bg-[rgba(20,18,15,0.35)] max-md:block" onClick={onCloseOutline}>
          <aside
            onClick={(e) => e.stopPropagation()}
            className="h-full w-[min(300px,85vw)] animate-pop-in overflow-y-auto border-r-[0.5px] border-divider bg-surface shadow-e3"
          >
            {toc}
          </aside>
        </div>
      )}
      <div ref={scrollRef} onScroll={onScroll} className="relative min-h-0 overflow-y-auto">
        <div className="mx-auto max-w-[820px] px-8 pb-24 pt-6 max-md:px-4">
          {sections.map((s) => (
            <section key={s.id} data-section-id={s.id} className="border-b-[0.5px] border-divider py-5 last:border-b-0">
              <SectionHeading section={s} />
              <RenderedSectionBody body={pipeTablesToHtml(resolveAssets(s.text, docId))} className="text-[13.5px]" />
            </section>
          ))}
          {error ? (
            <div className="py-6 text-center text-[12.5px] text-danger">
              {error}
              <button
                onClick={() => {
                  setError(null);
                  void loadUntil(loadedRef.current.length + PAGE);
                }}
                className="ml-2 underline"
              >
                やり直す
              </button>
            </div>
          ) : !done ? (
            <div ref={sentinelRef} className="grid h-20 place-items-center">
              <span className="h-5 w-5 animate-[ar-spin_0.8s_linear_infinite] rounded-full border-2 border-divider-strong border-t-accent" />
            </div>
          ) : sections.length === 0 ? (
            <div className="py-16 text-center text-[13px] text-muted">本文がありません</div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** heading_path（「章 > 節」）の最後の見出し。 */
function headingOf(path: string): string {
  const parts = path.split(/\s*>\s*/).filter(Boolean);
  return parts[parts.length - 1] ?? "";
}

function SectionHeading({ section: s }: { section: SectionOut }) {
  const parts = s.heading_path.split(/\s*>\s*/).filter(Boolean);
  const title = parts.pop();
  const pages =
    s.page_start == null ? null : s.page_end && s.page_end !== s.page_start ? `p.${s.page_start}–${s.page_end}` : `p.${s.page_start}`;
  if (!title && !pages) return null;
  return (
    <div className="mb-2.5">
      {parts.length > 0 && <div className="mb-0.5 truncate text-[11px] text-muted-2">{parts.join(" › ")}</div>}
      <div className="flex items-baseline gap-2">
        {title && (
          <h3 className={cn("m-0 min-w-0 flex-1 font-bold text-fg", s.level <= 1 ? "text-[17px]" : s.level === 2 ? "text-[15px]" : "text-[14px]")}>
            {title}
          </h3>
        )}
        {pages && <span className="ml-auto shrink-0 font-mono text-[10.5px] text-muted-2">{pages}</span>}
      </div>
    </div>
  );
}

// ── 原本 ─────────────────────────────────────────────────────────────────

function OriginalPane({ doc, onShowParsed }: { doc: DocumentOut; onShowParsed?: () => void }) {
  const kind = getTextPreviewKind(doc.filename);
  if (kind) return <TextOriginal docId={doc.id} kind={kind} />;
  return <OriginalPreview docId={doc.id} filename={doc.filename} onShowParsed={onShowParsed} />;
}

/** テキスト系の原本を文字列として見せる（R8: 1 MB まで）。 */
function TextOriginal({ docId, kind }: { docId: string; kind: string }) {
  const [state, setState] = useState<{ text: string; truncated: boolean } | { error: string } | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    (async () => {
      const res = await fetch(originalUrl(docId), { signal: ctrl.signal });
      if (!res.ok || !res.body) throw new Error(String(res.status));
      const reader = res.body.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      let truncated = false;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        size += value.length;
        if (size > TEXT_LIMIT) {
          truncated = true;
          await reader.cancel();
          break;
        }
      }
      const buf = new Uint8Array(Math.min(size, TEXT_LIMIT));
      let at = 0;
      for (const c of chunks) {
        const part = c.subarray(0, Math.min(c.length, buf.length - at));
        buf.set(part, at);
        at += part.length;
        if (at >= buf.length) break;
      }
      let text = new TextDecoder("utf-8").decode(buf);
      if (kind === "json" && !truncated) {
        try {
          text = JSON.stringify(JSON.parse(text), null, 2);
        } catch {
          // 整形できなければそのまま
        }
      }
      setState({ text, truncated });
    })().catch((e: unknown) => {
      if (!ctrl.signal.aborted) setState({ error: e instanceof Error ? e.message : "" });
    });
    return () => ctrl.abort();
  }, [docId, kind]);

  if (state === null) {
    return (
      <div className="grid h-full place-items-center">
        <span className="h-6 w-6 animate-[ar-spin_0.8s_linear_infinite] rounded-full border-2 border-divider-strong border-t-accent" />
      </div>
    );
  }
  if ("error" in state) {
    return <div className="grid h-full place-items-center text-[12.5px] text-danger">原本を読み込めませんでした</div>;
  }
  const mono = kind !== "markdown";
  return (
    <div className="h-full overflow-auto">
      {state.truncated && (
        <div className="sticky top-0 border-b-[0.5px] border-divider bg-surface-2 px-4 py-2 text-[11.5px] text-muted">
          大きいファイルのため、先頭 {formatBytes(TEXT_LIMIT)} だけを表示しています。全体はダウンロードしてご覧ください。
        </div>
      )}
      <pre
        className={cn(
          "m-0 mx-auto max-w-[900px] whitespace-pre-wrap px-8 py-6 text-fg-2 [overflow-wrap:anywhere] max-md:px-4",
          mono ? "font-mono text-[12px] leading-[1.6]" : "font-sans text-[13.5px] leading-[1.75]",
        )}
      >
        {state.text}
      </pre>
    </div>
  );
}
