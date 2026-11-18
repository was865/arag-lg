"use client";

import { Fragment } from "react";
import { cn } from "@/lib/utils";
import { useT } from "@/i18n/context";
import type { ThreadSearchState } from "@/hooks/use-thread-search";
import type { ThreadSummary } from "@/lib/types";

/** 文を、検索語（大文字小文字は区別しない）に当たる部分とそれ以外に分ける。奇数番目が当たった部分。 */
export function highlightParts(text: string, terms: string[]): string[] {
  const ts = terms.filter(Boolean).map((x) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (ts.length === 0) return [text];
  // 長い語から当てる（「8月」と「8」があれば「8月」を 1 つにまとめる）
  ts.sort((a, b) => b.length - a.length);
  return text.split(new RegExp(`(${ts.join("|")})`, "gi"));
}

function Highlight({ text, terms }: { text: string; terms: string[] }) {
  return (
    <>
      {highlightParts(text, terms).map((p, i) =>
        i % 2 === 1 ? (
          <mark key={i} className="rounded-[2px] bg-accent/15 px-px text-fg">{p}</mark>
        ) : (
          <Fragment key={i}>{p}</Fragment>
        ),
      )}
    </>
  );
}

/** サイドバーの検索結果（specs/022 R3）。題名に当たれば題名だけ、本文に当たれば前後の文も出す。 */
export function SidebarSearchResults({
  query, state, localMatches, activeThreadId, onSelect,
}: {
  query: string;
  state: ThreadSearchState;
  /** サーバーの結果が来るまで出す、題名だけの絞り込み。 */
  localMatches: ThreadSummary[];
  activeThreadId: string;
  onSelect: (id: string) => void;
}) {
  const { t } = useT();
  const terms = query.trim().split(/\s+/);
  const rows =
    state.status === "done"
      ? state.items.map((h) => ({
          id: h.thread.id,
          title: h.thread.title,
          snippet: h.match === "title" ? null : h.snippet,
          where: h.match === "query" ? t.sidebar.searchMatchQuery : h.match === "answer" ? t.sidebar.searchMatchAnswer : null,
        }))
      : localMatches.map((th) => ({ id: th.id, title: th.title, snippet: null, where: null }));

  return (
    <div className="mb-2">
      <div className="flex items-baseline justify-between px-2 pb-1 pt-2 eyebrow">
        <span>{t.sidebar.searchResults}</span>
        {state.status === "loading" && <span className="font-normal normal-case tracking-normal">{t.sidebar.searchSearching}</span>}
      </div>
      {rows.map((r) => (
        <button
          key={r.id}
          onClick={() => onSelect(r.id)}
          className={cn(
            "my-px block w-full rounded-control px-2 py-1.5 text-left transition-colors",
            r.id === activeThreadId ? "bg-surface shadow-e1" : "hover:bg-divider",
          )}
        >
          <span className="block truncate text-footnote text-fg">
            <Highlight text={r.title} terms={terms} />
          </span>
          {r.snippet && (
            <span className="mt-0.5 line-clamp-2 text-caption leading-[1.45] text-muted">
              {r.where && <span className="mr-1 text-muted-2">{r.where}:</span>}
              <Highlight text={r.snippet} terms={terms} />
            </span>
          )}
        </button>
      ))}
      {rows.length === 0 && state.status !== "loading" && (
        <div className="px-2 py-3 text-footnote text-muted-2">
          {state.status === "error" ? t.sidebar.searchFailed : t.sidebar.searchEmpty}
        </div>
      )}
    </div>
  );
}
