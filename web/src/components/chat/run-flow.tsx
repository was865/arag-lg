"use client";

import { Fragment } from "react";
import { cn, formatMs } from "@/lib/utils";
import type { FlowNodeId, FlowRoute, FlowRun, FlowStop } from "@/lib/chat/flow";
import type { Dictionary } from "@/i18n/dictionary";
import { interpolate } from "@/i18n/interpolate";
import { useT } from "@/i18n/context";

/** 実行中の見出しで並べる節点（見張り・画像・続けて聞くは前後の節点にまとめる）。 */
const COMPACT: FlowNodeId[] = ["understand", "primer_search", "investigate", "review", "finalize"];
const COMPACT_OF: Partial<Record<FlowNodeId, FlowNodeId>> = {
  read_image: "understand",
  guard: "investigate",
  followups: "finalize",
};

/** 実行中の見出しの段階の列（今の節点だけ色と呼吸する点）。流れの表示と同じ計算から出す。 */
export function FlowRail({ flow }: { flow: FlowRun }) {
  const current = flow.current ? (COMPACT_OF[flow.current] ?? flow.current) : undefined;
  const byId = new Map(flow.nodes.map((n) => [n.id, n]));
  // 雑談と分かったら、最初の検索は列から外す（通らない段階を待っているように見せない）
  const chat = flow.edges.some((e) => e.key === "chat" && e.passed);
  const ids = COMPACT.filter((id) => !(chat && id === "primer_search"));
  const at = current ? ids.indexOf(current) : -1;
  return (
    <span className="inline-flex items-center gap-1" aria-hidden>
      {ids.map((id, i) => {
        const done = i < at || (at < 0 && byId.get(id)?.passed);
        return (
          <Fragment key={id}>
            {i > 0 && (
              <span
                className={cn(
                  "h-px w-2.5 transition-colors duration-(--duration-mid)",
                  i <= at ? "bg-accent/50" : "bg-divider-strong",
                )}
              />
            )}
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-full px-1.5 py-px text-caption transition-colors duration-(--duration-mid)",
                i === at ? "bg-accent-soft font-medium text-accent" : done ? "text-fg-2" : "text-muted-2",
              )}
            >
              {i === at && <span className="h-1.5 w-1.5 animate-breathe rounded-full bg-accent motion-reduce:animate-none" />}
              {byId.get(id)?.label}
            </span>
          </Fragment>
        );
      })}
    </span>
  );
}

// ── 「詳細」の流れ（実際にたどった順の経路。specs/029 R7〜R9） ──

/** 停留所の短い説明（何をしたか）。 */
function detailOf(s: FlowStop, t: Dictionary): string {
  const c = t.chat;
  switch (s.node) {
    case "understand": {
      const kind = (s.steps.at(-1)?.output as Record<string, unknown> | null | undefined)?.kind;
      return kind === "chat" ? c.understandKindChat : kind === "docs" ? c.understandKindDocs : "";
    }
    case "primer_search":
      return interpolate(c.flowSearches, { n: String(s.steps.length) });
    case "investigate": {
      // 使ったツールを名前ごとに数える（推論の記録は除く）
      const counts = new Map<string, number>();
      for (const x of s.steps) {
        if (x.name === "reasoning") continue;
        const label = x.label || x.name;
        counts.set(label, (counts.get(label) ?? 0) + 1);
      }
      if (!counts.size) return s.round > 1 ? c.flowRewrite : c.flowCompose;
      return [...counts].map(([k, n]) => (n > 1 ? `${k} ${n}` : k)).join("・");
    }
    case "guard": {
      const kind = s.steps[0]?.input?.kind;
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
      const q = (s.steps.at(-1)?.output as Record<string, unknown> | null | undefined)?.questions;
      return Array.isArray(q) ? interpolate(c.flowFollowups, { n: String(q.length) }) : (s.steps.at(-1)?.summary ?? "");
    }
    default:
      return s.steps.at(-1)?.summary ?? "";
  }
}

/** 経路をひと言で（流れの見出しの右）。 */
function summaryOf(r: FlowRoute, running: boolean, t: Dictionary): string {
  const c = t.chat;
  if (running) return c.flowSummaryRunning;
  if (r.usedDraft) return c.flowSummaryUsedDraft;
  if (r.sentBack > 0) return interpolate(c.flowSummarySentBack, { n: String(r.sentBack) });
  if (r.chat) return c.flowSummaryChat;
  return c.flowSummaryPassed;
}

/** 停留所の印。済み・差し戻し・通過・退避・失敗・いまの段階を、形と少しの色で見分ける。 */
function StopMark({ s }: { s: FlowStop }) {
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
  switch (s.outcome) {
    case "sent_back": // 戻る矢印
      return <span className={cn(base, "bg-accent-soft text-accent")}>{glyph("M6 4L3 7l3 3M3.5 7H10a3 3 0 010 6H8")}</span>;
    case "passed":
      return (
        <span className={cn(base, "bg-accent text-surface", s.inferred && "bg-accent-soft text-accent")}>
          {glyph("M4 8.3l2.6 2.5L12 5.4")}
        </span>
      );
    case "used_draft":
    case "retried": // 回り込む矢印
      return <span className={cn(base, "bg-accent-soft text-accent")}>{glyph("M3 8a5 5 0 109-3M12 2v3H9")}</span>;
    case "failed":
      return <span className={cn(base, "bg-danger-soft text-danger")}>{glyph("M8 4.5v4M8 11.5v.01")}</span>;
    case "skipped":
      return <span className={cn(base, "border-[1.5px] border-divider-strong bg-surface text-muted-2")}>{glyph("M5.5 8h5")}</span>;
    default:
      return (
        <span className={cn(base, "border-[1.5px] border-accent/55 bg-surface")}>
          <span className="h-1.5 w-1.5 rounded-full bg-accent/80" />
        </span>
      );
  }
}

/**
 * この回答が実際にたどった順の流れ。差し戻されたら「2 周目」の調査・確認を続けて並べる（同じ節点を ×2 にまとめない）。
 * 幅があり停留所が少なければ横一列、狭いか長い経路は縦に並べる。停留所を押すと、そこで出たステップだけに一覧を絞る（R8）。
 */
export function RunFlow({
  route,
  running = false,
  selected,
  onSelect,
}: {
  route: FlowRoute;
  running?: boolean;
  selected?: string | null;
  onSelect?: (key: string | null) => void;
}) {
  const { t } = useT();
  const { stops } = route;
  // 横一列は 8 つまで（それより長い経路は縦の方が読みやすい）
  const wide = stops.length <= 8;
  const row = (cls: string) => (wide ? cls : "");
  const picked = stops.find((s) => s.key === selected);
  const name = (s: FlowStop) => (s.round > 1 ? `${s.label}（${interpolate(t.chat.flowRound, { n: String(s.round) })}）` : s.label);

  return (
    <div className="@container border-b-[0.5px] border-divider px-3.5 pb-3 pt-2.5 max-md:px-3">
      <div className="mb-2.5 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span className="text-caption font-semibold text-muted">{t.chat.flowTitle}</span>
        <span className="text-caption text-fg-2">{summaryOf(route, running, t)}</span>
        {route.inferred && <span className="ml-auto text-caption text-muted-2">{t.chat.flowInferred}</span>}
      </div>
      <ol className={cn("m-0 flex list-none flex-col p-0", row("@[480px]:flex-row"))}>
        {stops.map((s, i) => {
          const detail = detailOf(s, t);
          const active = selected === s.key;
          const usable = Boolean(onSelect) && s.stepIds.length > 0;
          const next = stops[i + 1];
          return (
            <li
              key={s.key}
              style={{ animationDelay: `${i * 45}ms` }}
              className={cn(
                "relative min-w-0 animate-fade-up pb-2.5 last:pb-0 motion-reduce:animate-none",
                row("@[480px]:flex-1 @[480px]:pb-0"),
              )}
            >
              {next && (
                // 次の停留所への線。差し戻しの後は、戻ってやり直す区間として点線にする
                <span
                  aria-hidden
                  style={{ animationDelay: `${i * 45 + 120}ms` }}
                  className={cn(
                    "absolute left-[7.5px] top-[19px] bottom-[3px] w-0 animate-draw border-l motion-reduce:animate-none",
                    row("@[480px]:bottom-auto @[480px]:left-[calc(50%+11px)] @[480px]:right-[calc(-50%+11px)] @[480px]:top-[7.5px] @[480px]:h-0 @[480px]:w-auto @[480px]:border-l-0 @[480px]:border-t"),
                    s.outcome === "sent_back" || s.outcome === "retried"
                      ? "border-dashed border-accent/60"
                      : "border-accent/35",
                  )}
                />
              )}
              <button
                type="button"
                disabled={!usable}
                aria-pressed={active}
                title={usable ? undefined : t.chat.flowNoSteps}
                onClick={() => onSelect?.(active ? null : s.key)}
                className={cn(
                  "group flex w-full min-w-0 items-start gap-2.5 rounded-control border-0 bg-transparent p-0 text-left outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
                  row("@[480px]:flex-col @[480px]:items-center @[480px]:gap-1.5 @[480px]:px-1 @[480px]:text-center"),
                  usable ? "cursor-pointer" : "cursor-default",
                )}
              >
                <span className={cn("rounded-full transition-shadow duration-(--duration-mid)", active && "ring-[3px] ring-accent/25")}>
                  <StopMark s={s} />
                </span>
                <span className={cn("flex min-w-0 flex-1 items-baseline gap-2", row("@[480px]:w-full @[480px]:flex-col @[480px]:items-center @[480px]:gap-0"))}>
                  <span
                    className={cn(
                      "shrink-0 text-footnote font-medium transition-colors duration-(--duration-mid)",
                      active || s.current ? "text-accent" : "text-fg",
                      usable && "group-hover:text-accent",
                      row("@[480px]:max-w-full @[480px]:truncate @[480px]:text-caption"),
                    )}
                  >
                    {name(s)}
                  </span>
                  <span
                    className={cn(
                      "min-w-0 flex-1 truncate text-caption",
                      s.outcome === "sent_back" || s.outcome === "used_draft" ? "text-accent" : "text-muted",
                      s.outcome === "failed" && "text-danger",
                      // 横一列では 2 行まで折り返す（理由が切れて読めないのを防ぐ）
                      row("@[480px]:line-clamp-2 @[480px]:w-full @[480px]:flex-none @[480px]:whitespace-pre-line @[480px]:leading-snug"),
                    )}
                    title={detail.replace("\n", " ")}
                  >
                    {detail}
                  </span>
                  {s.durationMs > 0 && (
                    <span className={cn("nums shrink-0 font-mono text-[10px] text-muted-2", row("@[480px]:mt-0.5"))}>
                      {formatMs(s.durationMs)}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      {picked && onSelect && (
        <div className="mt-2.5 flex animate-fade-in items-center gap-1.5 text-caption text-muted motion-reduce:animate-none">
          <span>{interpolate(t.chat.flowFiltered, { node: name(picked) })}</span>
          <span aria-hidden>·</span>
          <button
            type="button"
            onClick={() => onSelect(null)}
            className="border-0 bg-transparent p-0 text-caption text-accent underline-offset-2 hover:underline"
          >
            {t.chat.flowClear}
          </button>
        </div>
      )}
    </div>
  );
}
