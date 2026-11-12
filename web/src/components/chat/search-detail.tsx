"use client";

/**
 * 検索の明細（「詳細」の中。specs/025 見直し）。
 * - いちばん上に「何という語で探したか」を出し、方式と件数は小さく添える（入力を大きな箱にしない）。
 * - 見つけた箇所は文書ごとにまとめる（同じ文書の題を何度も並べない）。箇所は見出しの名前だけを出す。
 * - 回答に引用した文書には印を付ける（探したものと、使ったものの関係が分かる）。
 */
import { createContext, useContext } from "react";
import { Icon } from "@/components/icons";
import { Badge } from "@/components/ui/badge";
import { groupHits, scoreScale, searchModeLabel } from "@/lib/chat/evidence";
import { getFileMeta } from "@/lib/file-types";
import type { ToolCall } from "@/lib/types";
import { useT } from "@/i18n/context";
import { interpolate } from "@/i18n/interpolate";

/** この回答が引用した文書の題（AgentActivity が渡す）。 */
export const CitedTitlesContext = createContext<ReadonlySet<string>>(new Set());

export interface SearchHit {
  title: string;
  heading: string;
  score: number;
}

/** 検索の段階で、明細を出せるもの（見つけた箇所が 1 つ以上ある）か。 */
export function searchHits(step: ToolCall): SearchHit[] | null {
  if (step.name !== "vector_search" && step.name !== "bm25_search") return null;
  const hits = step.output?.hits;
  return Array.isArray(hits) && hits.length > 0 ? (hits as SearchHit[]) : null;
}

export function SearchDetail({ step, hits }: { step: ToolCall; hits: SearchHit[] }) {
  const { t } = useT();
  const cited = useContext(CitedTitlesContext);
  const groups = groupHits(hits, cited);
  const scale = scoreScale(hits);
  const query = typeof step.input.query === "string" ? step.input.query : "";
  return (
    <div className="grid gap-2 py-1">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-footnote">
        <span className="text-muted">
          <Icon name="search" size={12} />
        </span>
        {query && <span className="min-w-0 font-medium text-fg [overflow-wrap:anywhere]">「{query}」</span>}
        <Badge>{searchModeLabel(step.input.mode, step.name)}</Badge>
        <span className="nums text-caption text-muted">
          {interpolate(t.chat.searchFound, { docs: String(groups.length), spots: String(hits.length) })}
        </span>
      </div>
      <ul className="m-0 grid max-h-80 list-none gap-1.5 overflow-y-auto p-0">
        {groups.map((g) => {
          const meta = getFileMeta(g.title);
          return (
            <li key={g.title} className="rounded-control border-[0.5px] border-divider-strong bg-surface px-2.5 py-2">
              <div className="flex min-w-0 items-center gap-2 text-footnote">
                <span className="shrink-0" style={{ color: meta.color }}>
                  <Icon name={meta.iconName} size={13} />
                </span>
                <span className="min-w-0 truncate font-medium text-fg" title={g.title}>
                  {g.title}
                </span>
                {g.cited && <Badge tone="accent">{t.chat.searchCited}</Badge>}
                <span className="nums ml-auto shrink-0 font-mono text-caption text-muted">{g.best.toFixed(2)}</span>
              </div>
              <ul className="m-0 mt-1.5 grid list-none gap-1 p-0 pl-[21px]">
                {g.sections.map((s, i) => (
                  <li key={i} className="grid grid-cols-[minmax(0,1fr)_48px_30px] items-center gap-2.5 text-caption">
                    <span className="truncate text-fg-2">{s.label || t.chat.searchDocTop}</span>
                    <span className="h-[3px] overflow-hidden rounded-full bg-divider" aria-hidden>
                      <span className="block h-full rounded-full bg-fg/45" style={{ width: `${Math.max(4, (s.score / scale) * 100)}%` }} />
                    </span>
                    <span className="nums text-right font-mono text-mini text-muted-2">{s.score.toFixed(2)}</span>
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
