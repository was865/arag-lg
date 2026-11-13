"use client";

import { Fragment } from "react";
import { cn, formatMs } from "@/lib/utils";
import type { FlowNodeId, FlowRun } from "@/lib/chat/flow";
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

/**
 * この回答が通った流れ（specs/029 R7〜R9）。節点を左から右に並べ、通った節点を強く、通らなかったものを薄く見せる。
 * 戻り（差し戻し・やり直し）は上の弧、下書きへの退避は下の弧。節点を押すと、その節点のステップだけに一覧を絞る。
 */
export function RunFlow({
  flow,
  selected,
  onSelect,
}: {
  flow: FlowRun;
  selected?: FlowNodeId | null;
  onSelect?: (node: FlowNodeId | null) => void;
}) {
  const { t } = useT();
  // 画像の読み取りは、画像のあるターンだけ並べる（いつも薄い札が 1 つ余ると、流れが読みにくい）
  const nodes = flow.nodes.filter((n) => n.id !== "read_image" || n.passed);
  const col = (id: FlowNodeId) => nodes.findIndex((n) => n.id === id);
  const pct = (i: number) => `${((i + 0.5) / nodes.length) * 100}%`;
  const arc = (from: FlowNodeId, to: FlowNodeId) => {
    const [a, b] = [col(from), col(to)].sort((x, y) => x - y);
    return { left: pct(a), width: `${((b - a) / nodes.length) * 100}%` };
  };
  const notes: { key: string; text: string; from: FlowNodeId; to: FlowNodeId; below?: boolean }[] = [];
  if (flow.sentBack > 0)
    notes.push({ key: "back", text: interpolate(t.chat.flowSentBack, { n: String(flow.sentBack) }), from: "investigate", to: "review" });
  if (flow.retried > 0)
    notes.push({ key: "retry", text: interpolate(t.chat.flowRetried, { n: String(flow.retried) }), from: "investigate", to: "guard" });
  if (flow.usedDraft) notes.push({ key: "draft", text: t.chat.flowUsedDraft, from: "guard", to: "finalize", below: true });
  const above = notes.filter((n) => !n.below);
  const below = notes.filter((n) => n.below);

  const Arc = ({ n, down }: { n: (typeof notes)[number]; down?: boolean }) => (
    <div className="relative h-5" aria-hidden>
      <div
        className={cn(
          "absolute h-2.5 border-accent/60",
          down ? "top-0 rounded-b-md border-x border-b border-dashed" : "bottom-0 rounded-t-md border-x border-t",
        )}
        style={arc(n.from, n.to)}
      />
      <span
        className={cn(
          "absolute -translate-x-1/2 whitespace-nowrap rounded-full bg-surface-2 px-1.5 text-caption text-accent",
          down ? "top-1" : "-top-0.5",
        )}
        style={{ left: `calc(${arc(n.from, n.to).left} + ${arc(n.from, n.to).width} / 2)` }}
      >
        {n.text}
      </span>
    </div>
  );

  return (
    <div className="flex flex-col gap-0.5 border-b-[0.5px] border-divider px-3.5 pb-2.5 pt-2 max-md:px-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-caption font-semibold text-muted">{t.chat.flowTitle}</span>
        {flow.inferred && <span className="text-caption text-muted-2">{t.chat.flowInferred}</span>}
      </div>
      {above.map((n) => (
        <Arc key={n.key} n={n} />
      ))}
      <div className="grid" style={{ gridTemplateColumns: `repeat(${nodes.length}, minmax(0, 1fr))` }}>
        {nodes.map((n, i) => {
          const next = nodes[i + 1];
          const linkPassed = next && n.passed && next.passed;
          const active = selected === n.id;
          const usable = n.passed && n.stepIds.length > 0 && onSelect;
          return (
            <div key={n.id} className="relative flex min-w-0 justify-center">
              {next && (
                <span
                  aria-hidden
                  className={cn(
                    "absolute left-1/2 top-1/2 w-full border-t",
                    linkPassed ? "border-accent/40" : "border-dashed border-divider-strong",
                  )}
                />
              )}
              <button
                type="button"
                disabled={!usable}
                onClick={() => onSelect?.(active ? null : n.id)}
                title={n.description}
                aria-pressed={active}
                className={cn(
                  "relative z-[1] inline-flex min-w-0 max-w-full flex-col items-center rounded-control border-[0.5px] px-1.5 py-0.5 text-caption max-sm:px-1 leading-tight outline-none transition-colors duration-(--duration-mid) focus-visible:ring-2 focus-visible:ring-accent/50",
                  n.passed ? "border-divider-strong bg-surface text-fg" : "border-dashed border-divider bg-surface-2 text-muted-2",
                  n.current && "border-accent/60 text-accent",
                  active && "ring-2 ring-accent/60",
                  usable ? "cursor-pointer hover:border-accent/50" : "cursor-default",
                )}
              >
                <span className="inline-flex max-w-full items-center gap-1">
                  {n.current && <span className="h-1.5 w-1.5 shrink-0 animate-breathe rounded-full bg-accent motion-reduce:animate-none" />}
                  {/* 幅が足りないときは切らずに折り返す（「最初の / 検索」）。横スクロールはさせない */}
                  <span className="truncate max-sm:whitespace-normal max-sm:text-center max-sm:[word-break:break-all]">{n.label}</span>
                </span>
                {/* 2 行目: 通った回数と所要時間（幅が足りないときは回数だけ） */}
                {(n.visits > 1 || (n.passed && n.durationMs > 0)) && (
                  <span className="inline-flex items-center gap-1 font-mono text-[10px] text-muted">
                    {n.visits > 1 && <span className="nums font-sans font-medium text-accent">×{n.visits}</span>}
                    {n.passed && n.durationMs > 0 && <span className="nums max-sm:hidden">{formatMs(n.durationMs)}</span>}
                  </span>
                )}
              </button>
            </div>
          );
        })}
      </div>
      {below.map((n) => (
        <Arc key={n.key} n={n} down />
      ))}
      {selected && onSelect && (
        <div className="mt-1 flex items-center gap-1.5 text-caption text-muted">
          <span>{interpolate(t.chat.flowFiltered, { node: flow.nodes.find((n) => n.id === selected)?.label ?? selected })}</span>
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
