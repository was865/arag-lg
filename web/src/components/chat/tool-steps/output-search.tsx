/** 検索系の段階の出力（候補のスコア・rerank・広げた範囲・選別・取り出した資料）。 */
import { parseRetrieveHits } from "@/lib/chat/evidence";
import { cn } from "@/lib/utils";
import { Icon } from "@/components/icons";
import type { RerankHit, ToolCall } from "@/lib/types";
import { interpolate } from "@/i18n/interpolate";
import type { Dictionary } from "@/i18n/dictionary";
import { CandidateHit, ExpandedHit, GradeCandidate, KeyValueGrid, boxCls, preCls } from "./shared";

type Out = Record<string, unknown>;

/** rerank で残した候補とスコア */
export function RerankOutput({ selected }: { selected: RerankHit[] }) {
  return (
    <div className="flex flex-col gap-[5px] py-1">
      {selected.map((s) => (
        <div
          key={s.id}
          className="grid grid-cols-[80px_42px_1fr] items-center gap-2.5 text-caption max-md:grid-cols-[90px_38px_1fr] max-md:gap-2"
        >
          <div className="h-[5px] overflow-hidden rounded-full bg-divider">
            <span className="block h-full rounded-full bg-accent" style={{ width: `${s.score * 100}%` }} />
          </div>
          <span className="font-mono text-caption font-semibold text-accent">{s.score.toFixed(2)}</span>
          <span className="truncate text-fg-2">{s.title}</span>
        </div>
      ))}
    </div>
  );
}

/** 検索の候補（ベクトル・BM25・混合）。0 件なら言い換えの知らせか「候補なし」 */
export function HitsOutput({ step, output, t }: { step: ToolCall; output: Out; t: Dictionary }) {
  const hits = output.hits as CandidateHit[];
  if (hits.length === 0) {
    if (output.fallback) {
      const terms = Array.isArray(output.terms)
        ? (output.terms as unknown[]).map(String)
        : String(step.input.query ?? "").split(/\s+/).filter(Boolean);
      return (
        <div className="flex items-start gap-1.5 rounded-control bg-surface-2 px-2.5 py-2 text-caption leading-[1.6] text-fg-2">
          <Icon name="info" size={12} className="mt-[3px] shrink-0 text-muted" />
          <span>
            {interpolate(output.fallback === "codes" ? t.chat.keywordRelax : t.chat.keywordFallback, {
              terms: terms.map((x) => `「${x}」`).join(""),
            })}
          </span>
        </div>
      );
    }
    return <div className="px-1 py-1 text-caption text-muted">{t.chat.noCandidates}</div>;
  }
  // スコアは非負前提（dense=cosine, sparse=BM25/dot）。リスト内最大値でバー幅を正規化。
  const max = Math.max(...hits.map((h) => h.score), 1e-9);
  return (
    <div className="flex max-h-72 flex-col gap-[5px] overflow-y-auto py-1">
      {hits.map((h, i) => (
        <div
          key={i}
          className="grid grid-cols-[64px_42px_1fr] items-center gap-2.5 text-caption max-md:grid-cols-[54px_38px_1fr] max-md:gap-2"
        >
          <div className="h-[5px] overflow-hidden rounded-full bg-divider">
            <span className="block h-full rounded-full bg-accent" style={{ width: `${Math.max(4, (h.score / max) * 100)}%` }} />
          </div>
          <span className="font-mono text-caption font-semibold text-accent">{h.score.toFixed(2)}</span>
          <span className="truncate text-fg-2">
            <span className="text-fg">{h.title}</span>
            {h.heading && <span className="text-muted-2"> — {h.heading}</span>}
          </span>
        </div>
      ))}
    </div>
  );
}

/** 前後を広げて読んだ範囲 */
export function ExpandOutput({ output, t }: { output: Out; t: Dictionary }) {
  const expanded = Array.isArray(output.expanded) ? (output.expanded as ExpandedHit[]) : [];
  if (expanded.length === 0) {
    return <KeyValueGrid rows={[{ k: t.chat.expandCount, v: String(output.count ?? 0) }]} />;
  }
  return (
    <div className="flex flex-col gap-2">
      <KeyValueGrid rows={[{ k: t.chat.expandCount, v: String(output.count ?? expanded.length) }]} />
      <div className="overflow-hidden rounded-control border-[0.5px] border-divider bg-code-bg">
        {expanded.map((h, i) => (
          <div key={`${h.id}-${i}`} className={cn("px-3 py-2.5", i > 0 && "border-t-[0.5px] border-divider")}>
            <div className="flex min-w-0 items-center gap-2">
              <span className="font-mono text-caption font-semibold tabular-nums text-accent">{h.score.toFixed(2)}</span>
              <span className="min-w-0 flex-1 truncate text-footnote font-medium text-fg">{h.title}</span>
              <span className="shrink-0 font-mono text-mini text-muted-2">p.{h.page}</span>
              <span className="shrink-0 font-mono text-mini text-muted-2">{h.expandedChars}ch</span>
            </div>
            {h.heading && <div className="mt-0.5 truncate font-mono text-mini text-muted-2">{h.heading}</div>}
            {h.preview && <div className="mt-1 line-clamp-2 whitespace-pre-wrap text-caption leading-[1.5] text-fg-2">{h.preview}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

/** 候補の選別（残す・外す） */
export function GradeOutput({ output }: { output: Out }) {
  const candidates = Array.isArray(output.candidates) ? (output.candidates as GradeCandidate[]) : [];
  if (candidates.length === 0) return <pre className={preCls}>{JSON.stringify(output, null, 2)}</pre>;
  return (
    <div className="flex flex-col gap-2">
      <KeyValueGrid rows={[
        { k: "kept", v: `${String(output.kept ?? 0)} / ${String(output.total ?? candidates.length)}` },
        { k: "retry", v: output.needRetry ? "yes" : "no" },
      ]} />
      <div className="overflow-hidden rounded-control border-[0.5px] border-divider bg-code-bg">
        {candidates.map((c, i) => (
          <div key={`${c.chunkId}-${i}`} className={cn("grid grid-cols-[58px_42px_1fr] items-start gap-2.5 px-3 py-2.5 text-caption", i > 0 && "border-t-[0.5px] border-divider")}>
            <span className={cn("rounded-full px-2 py-px text-center text-mini font-semibold", c.kept ? "bg-accent-soft text-accent" : "bg-divider text-muted")}>
              {c.kept ? "kept" : "skip"}
            </span>
            <span className="font-mono text-caption font-semibold tabular-nums text-accent">{c.score.toFixed(2)}</span>
            <span className="min-w-0">
              <span className="block truncate text-fg">{c.title}</span>
              {c.heading && <span className="block truncate font-mono text-mini text-muted-2">{c.heading}</span>}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** モデルに渡した資料（[n] 付き）。読めなければ本文をそのまま */
export function RetrievedOutput({ result }: { result: string }) {
  const hits = parseRetrieveHits(result);
  if (hits.length) {
    return (
      <div className="overflow-hidden rounded-control border-[0.5px] border-divider bg-code-bg">
        {hits.map((h, i) => (
          <div
            key={`${h.n}-${i}`}
            className={cn(
              "grid grid-cols-[28px_1fr] gap-2 px-3 py-2.5",
              i > 0 && "border-t-[0.5px] border-divider",
            )}
          >
            <span className="pt-px font-mono text-caption font-semibold text-accent">[{h.n}]</span>
            <div className="min-w-0">
              <div className="truncate text-footnote font-medium text-fg">{h.title}</div>
              <div className="truncate font-mono text-mini text-muted-2">{h.heading}</div>
              {h.snippet && (
                <div className="mt-1 line-clamp-3 whitespace-pre-wrap text-caption leading-[1.5] text-fg-2">
                  {h.snippet}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    );
  }
  // パースに失敗（"該当する資料は見つかりませんでした。" 等）した場合は本文をそのまま見せる。
  return (
    <div className={boxCls}>
      {result}
    </div>
  );
}
