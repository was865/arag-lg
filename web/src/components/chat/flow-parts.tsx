"use client";

/** 実行経路の部品（停留所の説明・印）。経路の一覧と、段階ごとのステップの一覧で同じものを使う（specs/029）。 */
import { cn } from "@/lib/utils";
import type { FlowStop } from "@/lib/chat/flow";
import type { Dictionary } from "@/i18n/dictionary";
import { interpolate } from "@/i18n/interpolate";

/** 停留所の短い説明（何をしたか）。 */
export function detailOf(s: FlowStop, t: Dictionary): string {
  const c = t.chat;
  switch (s.node) {
    case "understand": {
      const kind = (s.steps.at(-1)?.output as Record<string, unknown> | null | undefined)?.kind;
      return kind === "chat" ? c.understandKindChat : kind === "docs" ? c.understandKindDocs : "";
    }
    case "primer_search":
      return interpolate(c.flowSearches, { n: String(s.steps.length) });
    case "investigate": {
      // 使ったツールを名前ごとに数える（推論の記録・システムの処理（モデルの応答など）は除く）
      const counts = new Map<string, number>();
      for (const x of s.steps) {
        if (x.name === "reasoning" || x.name === "system") continue;
        const label = x.label || x.name;
        counts.set(label, (counts.get(label) ?? 0) + 1);
      }
      if (!counts.size) return s.round > 1 ? c.flowRewrite : c.flowCompose;
      return [...counts].map(([k, n]) => (n > 1 ? `${k} ${n}` : k)).join("・");
    }
    case "guard": {
      const kind = s.steps[0]?.input?.kind;
      if (s.outcome === "passed") return c.flowPassed;
      if (s.outcome === "retried") return c.flowRetried;
      if (s.outcome === "failed") return c.flowFailed;
      return kind === "rewrite_discarded" ? c.flowDiscarded : c.flowEmptyDraft;
    }
    case "review":
      return s.outcome === "sent_back"
        ? // 「表の集計の確認」→「表の集計」（停留所の名前が「確認」なので重ねない）
          // 横一列では理由を 2 行目に（語の途中で折り返さない）。縦では 1 行に続ける
          `${c.flowSentBack}\n${(s.steps[0]?.label ?? "").replace(/の(確認|見直し)$/, "")}`
        : s.outcome === "skipped"
          ? c.flowSkipped
          : c.flowPassed;
    case "finalize": {
      const names = [...new Set(s.steps.map((x) => x.label).filter(Boolean))];
      return names.length ? names.join("・") : c.flowFinalize;
    }
    case "followups": {
      if (s.notRun) return c.flowFollowupsOff;
      const q = (s.steps.at(-1)?.output as Record<string, unknown> | null | undefined)?.questions;
      return Array.isArray(q) ? interpolate(c.flowFollowups, { n: String(q.length) }) : (s.steps.at(-1)?.summary ?? "");
    }
    default:
      return s.steps.at(-1)?.summary ?? "";
  }
}

/** 停留所の印。形で見分ける（済み = 墨の点、差し戻し = 戻る矢印、通過 = ✓、退避・やり直し = 回り込む矢印、失敗 = !）。 */
export function StopMark({ s }: { s: FlowStop }) {
  const base = "relative z-[1] grid h-4 w-4 shrink-0 place-items-center rounded-full";
  if (s.current)
    return (
      <span className={cn(base, "border-[1.5px] border-accent bg-surface")}>
        <span className="h-1.5 w-1.5 animate-breathe rounded-full bg-accent motion-reduce:animate-none" />
      </span>
    );
  const glyph = (d: string) => (
    <svg viewBox="0 0 16 16" width="10" height="10" aria-hidden>
      <path d={d} stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
  if (s.notRun) return <span className={cn(base, "border-[1.5px] border-dashed border-divider-strong bg-surface")} />;
  const soft = cn(base, "border-[1.5px] border-muted/60 bg-surface text-fg-2");
  switch (s.outcome) {
    case "sent_back":
      return <span className={soft}>{glyph("M6 4L3 7l3 3M3.5 7H10a3 3 0 010 6H8")}</span>;
    case "passed":
      return <span className={cn(base, s.inferred ? "border-[1.5px] border-muted/60 bg-surface text-muted" : "bg-muted text-surface")}>{glyph("M4 8.3l2.6 2.5L12 5.4")}</span>;
    case "used_draft":
    case "retried":
      return <span className={soft}>{glyph("M3 8a5 5 0 109-3M12 2v3H9")}</span>;
    case "failed":
      return <span className={cn(base, "bg-danger-soft text-danger")}>{glyph("M8 4.5v4M8 11.5v.01")}</span>;
    case "skipped":
      return <span className={cn(base, "border-[1.5px] border-divider-strong bg-surface text-muted-2")}>{glyph("M5.5 8h5")}</span>;
    default:
      return (
        <span className={cn(base, "bg-surface")}>
          <span className="h-2.5 w-2.5 rounded-full bg-muted" />
        </span>
      );
  }
}

/** 回答を送った時点の印（送信のボタンと同じ上向きの矢印。朱は送信に使う色） */
export function SentMark() {
  return (
    <span className="relative z-[1] grid h-4 w-4 shrink-0 place-items-center rounded-full bg-accent-fill text-white">
      <svg viewBox="0 0 16 16" width="10" height="10" aria-hidden>
        <path d="M8 12.5V4M4.5 7.5L8 4l3.5 3.5" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}
