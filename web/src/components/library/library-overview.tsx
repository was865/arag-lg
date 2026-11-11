"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/icons";
import { libraryApi, type DocumentOut, type DocumentOverview } from "@/lib/library/api";
import { formatBytes, formatDate, formatRows, formatSegments } from "@/lib/library/view";
import { getFileMeta, isSpreadsheet } from "@/lib/file-types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const HIDE_KEY = "arag.library.overview.hidden";

function readHidden(): boolean {
  try {
    return window.localStorage.getItem(HIDE_KEY) === "1";
  } catch {
    return false;
  }
}

/** 概要を取り直す鍵（KB と、文書数・状態の内訳が変わったら取り直す）。 */
function useOverview(kbId: string | null, refreshKey: string): DocumentOverview | null {
  const key = `${kbId ?? ""}|${refreshKey}`;
  const [result, setResult] = useState<{ key: string; data: DocumentOverview } | null>(null);
  useEffect(() => {
    let alive = true;
    libraryApi.overview(kbId).then(
      (data) => alive && setResult({ key, data }),
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [kbId, key]);
  // KB を切り替えた直後は前の KB の概要を出さない（文書数の更新だけなら前の値を出したまま）
  return result && result.key.split("|")[0] === (kbId ?? "") ? result.data : null;
}

/** ライブラリのルートに出すナレッジベースの概要（specs/023 R2）。 */
export function LibraryOverview({
  kbId, title, refreshKey, onOpenDocument, onShowFailed,
}: {
  kbId: string | null;
  /** 明朝で出す題（ナレッジベースの名前） */
  title: string;
  refreshKey: string;
  onOpenDocument: (doc: DocumentOut) => void;
  onShowFailed: () => void;
}) {
  const ov = useOverview(kbId, refreshKey);
  const [hidden, setHidden] = useState(readHidden);
  const toggle = () => {
    setHidden((h) => {
      try {
        window.localStorage.setItem(HIDE_KEY, h ? "0" : "1");
      } catch {
        // 保存できなくても表示の切り替えはする
      }
      return !h;
    });
  };
  if (!ov || ov.documents === 0) return null;

  const busy = (ov.by_status.queued ?? 0) + (ov.by_status.running ?? 0);
  const failed = (ov.by_status.error ?? 0) + (ov.by_status.cancelled ?? 0);
  const segments = formatSegments(formatRows(ov.by_ext));

  return (
    <section aria-labelledby="kb-overview-title" className="mb-4 mt-3">
      {/* 題と件数を 1 行に（同じ数を何度も出さない。specs/025 R46） */}
      <div className="flex flex-wrap items-end gap-x-4 gap-y-1 px-2">
        <h2 id="kb-overview-title" className="m-0 min-w-0 flex-1 truncate font-display text-display font-bold text-fg max-md:basis-full">
          {title}
        </h2>
        <p className="m-0 flex items-baseline gap-1.5 text-caption text-muted">
          <span className="nums font-display text-hero font-bold leading-none text-fg max-md:text-display">
            {ov.documents.toLocaleString("ja-JP")}
          </span>
          <span>件 · {formatBytes(ov.total_bytes)}</span>
        </p>
        <Button variant="ghost" size="sm" className="h-6 gap-1 px-1.5 text-caption text-muted hover:text-fg"
          onClick={toggle}
          aria-expanded={!hidden}
        >
          {hidden ? "概要を表示" : "隠す"}
          <Icon name="chevronDown" size={10} className={cn("transition-transform", !hidden && "rotate-180")} />
        </Button>
      </div>
      {!hidden && (
        <div className="mt-2 grid gap-4 px-2">
          <p className="m-0 flex flex-wrap gap-x-4 gap-y-0.5 text-caption text-muted">
            {ov.added_7d > 0 && <span>この 7 日で <strong className="nums font-semibold text-fg-2">+{ov.added_7d.toLocaleString("ja-JP")}</strong> 件</span>}
            {ov.recent[0] && <span>最終追加 {formatDate(ov.recent[0].created_at)}</span>}
            {failed > 0 ? (
              <button onClick={onShowFailed} className="border-0 bg-transparent p-0 font-semibold text-danger underline-offset-2 hover:underline">
                失敗 {failed} 件を見る
              </button>
            ) : busy > 0 ? (
              <span className="font-semibold text-accent">処理中 {busy} 件</span>
            ) : (
              <span>すべて検索できます</span>
            )}
          </p>

          {/* 形式の内訳: 1 本の積み上げ棒 + 凡例 */}
          <div className="grid gap-2">
            <div className="flex h-2.5 gap-0.5 overflow-hidden rounded-full" role="img" aria-label={`形式の内訳: ${segments.map((f) => `${f.label} ${f.documents} 件`).join("、")}`}>
              {segments.map((f) => (
                <span key={f.label} className="block h-full first:rounded-l-full last:rounded-r-full" style={{ width: `${f.width}%`, backgroundColor: f.color }} />
              ))}
            </div>
            <ul className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1 p-0 text-caption text-muted">
              {segments.map((f) => (
                <li key={f.label} className="inline-flex items-center gap-1.5" title={formatBytes(f.bytes)}>
                  <span className="h-2 w-2 rounded-[2px]" style={{ backgroundColor: f.color }} aria-hidden />
                  {f.label}
                  <span className="nums font-mono text-fg-2">{f.documents.toLocaleString("ja-JP")}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* よく引用される文書: プレビュー付きのカード */}
          {ov.top_cited.length > 0 && (
            <div className="grid gap-2">
              <h3 className="m-0 flex items-baseline gap-2 text-mini font-semibold uppercase tracking-[0.06em] text-muted-2">
                よく引用される文書 <span className="font-normal normal-case tracking-normal">この 30 日の回答</span>
              </h3>
              <div className="grid grid-cols-4 gap-2.5 max-lg:grid-cols-2">
                {ov.top_cited.slice(0, 4).map((c, i) => (
                  <CitedCard key={c.document.id} doc={c.document} citations={c.citations} index={i} onOpen={onOpenDocument} />
                ))}
              </div>
            </div>
          )}

          {/* 最近の文書は下の一覧が新しい順なので出さない。失敗したものだけ目立たせる */}
          {ov.failed.length > 0 && (
            <Card title="処理に失敗した文書" tone="danger">
              <DocList items={ov.failed.map((d) => ({ doc: d, aside: formatDate(d.created_at) }))} onOpen={onOpenDocument} />
            </Card>
          )}
        </div>
      )}
    </section>
  );
}

/** 文書のカード。上は種類が分かる模様（表計算は格子、それ以外は行）、下は名前と引用回数。 */
function CitedCard({ doc, citations, index, onOpen }: { doc: DocumentOut; citations: number; index: number; onOpen: (d: DocumentOut) => void }) {
  const meta = getFileMeta(doc.filename);
  const sheet = isSpreadsheet(doc.filename);
  return (
    <button
      type="button"
      onClick={() => onOpen(doc)}
      title={doc.filename}
      style={{ animationDelay: `${index * 50}ms` }}
      className="group flex min-w-0 animate-fade-up flex-col overflow-hidden rounded-card border-[0.5px] border-divider-strong bg-surface p-0 text-left shadow-e1 outline-none transition-[transform,box-shadow] duration-(--duration-mid) ease-out hover:-translate-y-0.5 hover:shadow-e2 focus-visible:ring-2 focus-visible:ring-accent/50 motion-reduce:animate-none motion-reduce:hover:translate-y-0"
    >
      <span className="relative block h-[72px] border-b-[0.5px] border-divider bg-surface-2 px-3 py-2.5" aria-hidden>
        {sheet ? (
          <span className="grid grid-cols-4 gap-[3px]">
            {Array.from({ length: 12 }, (_, i) => (
              <span key={i} className={cn("h-2 rounded-[1.5px]", i === 5 ? "bg-accent-soft" : "bg-divider-strong")} />
            ))}
          </span>
        ) : (
          <span className="grid gap-[5px]">
            {[52, 100, 86, 70, 94].map((w, i) => (
              <span key={i} className={cn("rounded-[2px] bg-divider-strong", i === 0 ? "h-1.5" : "h-1")} style={{ width: `${w}%` }} />
            ))}
          </span>
        )}
        <span className="absolute bottom-1.5 right-2 rounded-[4px] px-1.5 py-px font-mono text-[9px] font-bold text-white" style={{ backgroundColor: meta.color }}>
          {meta.label}
        </span>
      </span>
      <span className="grid gap-0.5 px-2.5 py-2">
        <span className="truncate text-footnote font-semibold text-fg">{doc.filename}</span>
        <span className="flex items-center justify-between gap-2 text-mini text-muted">
          <span className="nums">{doc.page_count ? `${doc.page_count} ページ` : formatDate(doc.created_at)}</span>
          <span className="nums font-semibold text-accent">引用 {citations.toLocaleString("ja-JP")} 回</span>
        </span>
      </span>
    </button>
  );
}

function Card({ title, hint, tone, children }: { title: string; hint?: string; tone?: "danger"; children: React.ReactNode }) {
  return (
    <div className="min-w-0 rounded-card border-[0.5px] border-divider bg-surface px-3 py-2.5">
      <div className="mb-2 flex items-baseline gap-2">
        <h3 className={cn("m-0 text-footnote font-semibold", tone === "danger" ? "text-danger" : "text-fg")}>{title}</h3>
        {hint && <span className="text-caption text-muted-2">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

function DocList({ items, onOpen }: { items: { doc: DocumentOut; aside: string }[]; onOpen: (d: DocumentOut) => void }) {
  return (
    <ul className="m-0 grid list-none gap-px p-0">
      {items.map(({ doc, aside }) => (
        <li key={doc.id}>
          <button
            onClick={() => onOpen(doc)}
            className="-mx-1.5 flex w-[calc(100%+12px)] items-center gap-2 rounded-control px-1.5 py-1 text-left text-footnote hover:bg-divider"
          >
            <Icon name="doc" size={12} className="shrink-0 text-muted" />
            <span className="min-w-0 flex-1 truncate text-fg-2" title={doc.filename}>{doc.filename}</span>
            <span className="shrink-0 font-mono text-caption text-muted">{aside}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
