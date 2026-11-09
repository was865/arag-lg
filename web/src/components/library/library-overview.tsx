"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/icons";
import { libraryApi, type DocumentOut, type DocumentOverview } from "@/lib/library/api";
import { formatBytes, formatDate, formatRows } from "@/lib/library/view";
import { cn } from "@/lib/utils";

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
  kbId, refreshKey, onOpenDocument, onShowFailed,
}: {
  kbId: string | null;
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
  const ready = ov.by_status.ready ?? 0;
  const formats = formatRows(ov.by_ext);
  const maxDocs = Math.max(...formats.map((f) => f.documents), 1);

  return (
    <section aria-labelledby="kb-overview-title" className="mb-3 mt-1">
      <div className="flex items-center justify-between px-2 py-1.5">
        <h2 id="kb-overview-title" className="m-0 text-[10.5px] font-semibold uppercase tracking-[0.06em] text-muted-2">
          概要
        </h2>
        <button
          onClick={toggle}
          aria-expanded={!hidden}
          className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-muted hover:bg-divider hover:text-fg"
        >
          {hidden ? "表示" : "隠す"}
          <Icon name="chevronDown" size={10} className={cn("transition-transform", !hidden && "rotate-180")} />
        </button>
      </div>
      {!hidden && (
        <div className="grid gap-3">
          <div className="grid grid-cols-3 gap-2 max-md:gap-1.5">
            <Tile label="文書" value={ov.documents.toLocaleString("ja-JP")} unit="件" note={formatBytes(ov.total_bytes)} />
            <Tile
              label="この 7 日の追加"
              value={ov.added_7d.toLocaleString("ja-JP")}
              unit="件"
              note={ov.recent[0] ? `最新 ${formatDate(ov.recent[0].created_at)}` : undefined}
            />
            <Tile
              label="検索できる文書"
              value={ready.toLocaleString("ja-JP")}
              unit="件"
              note={
                failed > 0 ? (
                  <button onClick={onShowFailed} className="text-danger underline-offset-2 hover:underline">
                    失敗 {failed} 件を見る
                  </button>
                ) : busy > 0 ? (
                  `処理中 ${busy} 件`
                ) : (
                  "すべて処理済み"
                )
              }
            />
          </div>

          <div className="grid grid-cols-2 gap-2 max-lg:grid-cols-1">
            <Card title="形式の内訳">
              <ul className="m-0 grid list-none gap-1.5 p-0">
                {formats.map((f) => (
                  <li key={f.label} className="grid grid-cols-[84px_minmax(0,1fr)_auto] items-center gap-2 text-[12px]">
                    <span className="truncate text-fg-2">{f.label}</span>
                    <span className="h-1.5 overflow-hidden rounded-full bg-divider" aria-hidden>
                      <span
                        className="block h-full rounded-full bg-accent"
                        style={{ width: `${Math.max(2, (f.documents / maxDocs) * 100)}%` }}
                      />
                    </span>
                    <span className="font-mono text-[11px] text-muted" title={formatBytes(f.bytes)}>
                      {f.documents.toLocaleString("ja-JP")}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="よく引用される文書" hint="この 30 日の回答">
              {ov.top_cited.length === 0 ? (
                <p className="m-0 py-2 text-[12px] text-muted-2">まだ回答で引用されていません</p>
              ) : (
                <DocList
                  items={ov.top_cited.map((c) => ({ doc: c.document, aside: `${c.citations} 回` }))}
                  onOpen={onOpenDocument}
                />
              )}
            </Card>
          </div>

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

function Tile({ label, value, unit, note }: { label: string; value: string; unit: string; note?: React.ReactNode }) {
  return (
    <div className="min-w-0 rounded-[10px] border-[0.5px] border-divider bg-surface px-3 py-2.5 max-md:px-2.5 max-md:py-2">
      <div className="truncate text-[11px] text-muted">{label}</div>
      <div className="mt-0.5 flex items-baseline gap-1">
        <span className="text-[20px] font-semibold tabular-nums max-md:text-[17px] tracking-[-0.01em] text-fg">{value}</span>
        <span className="text-[11px] text-muted">{unit}</span>
      </div>
      {note && <div className="mt-0.5 truncate text-[11px] text-muted">{note}</div>}
    </div>
  );
}

function Card({ title, hint, tone, children }: { title: string; hint?: string; tone?: "danger"; children: React.ReactNode }) {
  return (
    <div className="min-w-0 rounded-[10px] border-[0.5px] border-divider bg-surface px-3 py-2.5">
      <div className="mb-2 flex items-baseline gap-2">
        <h3 className={cn("m-0 text-[12px] font-semibold", tone === "danger" ? "text-danger" : "text-fg")}>{title}</h3>
        {hint && <span className="text-[11px] text-muted-2">{hint}</span>}
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
            className="-mx-1.5 flex w-[calc(100%+12px)] items-center gap-2 rounded-md px-1.5 py-1 text-left text-[12px] hover:bg-divider"
          >
            <Icon name="doc" size={12} className="shrink-0 text-muted" />
            <span className="min-w-0 flex-1 truncate text-fg-2" title={doc.filename}>{doc.filename}</span>
            <span className="shrink-0 font-mono text-[11px] text-muted">{aside}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
