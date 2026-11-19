"use client";

/**
 * 段階ごとのステップの一覧（specs/029 T36）。上の「グラフの実行経路」の停留所と同じ区切り・同じ時間で並べる。
 * 各段階: 小見出し（名前と、その段階の時間）→ エージェントのステップ（検索など）→ その段階のシステムの処理（淡い行）。
 * 確定の後に「回答を送信」の区切りを置き、その後（続けて聞く）は回答の時間に入らないことを示す。
 * 時間はすべて右の 1 列にそろえ、段階の時間 = その段階の行の時間の合計（並行に動いたものは別に示す）。
 */
import { Fragment } from "react";
import { cn, formatMs } from "@/lib/utils";
import type { ToolCall } from "@/lib/types";
import type { FlowRoute, FlowStop } from "@/lib/chat/flow";
import type { Dictionary } from "@/i18n/dictionary";
import { interpolate } from "@/i18n/interpolate";
import { PurposeNote, SubStepRow, SubSteps, groupSteps } from "./index";
import { ToolStepCard, ToolStepTimeline } from "./step-views";

interface Stage {
  stop: FlowStop;
  tools: ToolCall[];
  system: ToolCall[];
}

/** 停留所ごとに、渡されたステップ（絞り込み済み）を分ける。どの停留所にも入らないものは最後にまとめる。 */
export function stagesOf(route: FlowRoute, steps: ToolCall[]): { stages: Stage[]; rest: ToolCall[] } {
  const roots = steps.filter((s) => !s.parentId);
  const used = new Set<string>();
  const stages: Stage[] = [];
  for (const stop of route.stops) {
    const ids = new Set(stop.stepIds);
    const own = roots.filter((s) => ids.has(s.id) && !used.has(s.id));
    own.forEach((s) => used.add(s.id));
    if (!own.length) continue;
    stages.push({ stop, tools: own.filter((s) => s.name !== "system"), system: own.filter((s) => s.name === "system") });
  }
  return { stages, rest: roots.filter((s) => !used.has(s.id)) };
}

export function StagedSteps({
  route,
  steps,
  variant,
  expandedMap,
  onToggleStep,
  durationMs,
  t,
}: {
  route: FlowRoute;
  steps: ToolCall[];
  variant: "card" | "timeline";
  expandedMap: Record<string, boolean>;
  onToggleStep: (id: string) => void;
  /** 回答を送るまでの時間（「回答を送信」の区切りに添える） */
  durationMs?: number;
  t: Dictionary;
}) {
  const { childrenOf } = groupSteps(steps);
  const { stages, rest } = stagesOf(route, steps);
  const name = (s: FlowStop) => (s.round > 1 ? `${s.label}（${interpolate(t.chat.flowRound, { n: String(s.round) })}）` : s.label);
  const pad = variant === "card" ? "px-3.5 max-md:px-3" : "";

  const tools = (list: ToolCall[]) =>
    list.map((s, i) =>
      variant === "card" ? (
        <div key={s.id}>
          <ToolStepCard step={s} expanded={!!expandedMap[s.id]} onToggle={() => onToggleStep(s.id)} t={t} hasChildren={childrenOf.has(s.id)} />
          {childrenOf.has(s.id) && expandedMap[s.id] && (
            <div className="animate-fade-up border-b-[0.5px] border-divider bg-surface px-3.5 py-2 pl-10 motion-reduce:animate-none max-md:pl-6">
              <PurposeNote step={s} />
              <SubSteps steps={childrenOf.get(s.id)} expandedMap={expandedMap} onToggleStep={onToggleStep} t={t} />
            </div>
          )}
        </div>
      ) : (
        <div key={s.id}>
          <ToolStepTimeline step={s} expanded={!!expandedMap[s.id]} onToggle={() => onToggleStep(s.id)} isLast={i === list.length - 1} t={t} hasChildren={childrenOf.has(s.id)} />
          {childrenOf.has(s.id) && expandedMap[s.id] && (
            <div className="mb-2 ml-[22px] animate-fade-up pl-1 motion-reduce:animate-none">
              <PurposeNote step={s} />
              <SubSteps steps={childrenOf.get(s.id)} expandedMap={expandedMap} onToggleStep={onToggleStep} t={t} />
            </div>
          )}
        </div>
      ),
    );

  // システムの処理は、その段階の中に淡い行で（右の時間の列は上の行とそろう）
  const system = (list: ToolCall[]) =>
    list.length > 0 && (
      <div data-system className={cn("flex flex-col gap-px py-1", pad, variant === "card" && "pl-[42px] max-md:pl-[34px]")}>
        {list.map((s) => (
          <SubStepRow key={s.id} step={s} expanded={!!expandedMap[s.id]} onToggle={() => onToggleStep(s.id)} t={t} />
        ))}
      </div>
    );

  return (
    <div className={cn("flex flex-col", variant === "timeline" && "px-3.5 pb-3 pt-1 max-md:px-3")}>
      {stages.map(({ stop, tools: tl, system: sys }, i) => {
        const sent = stop.node === "finalize" && durationMs && durationMs > 0;
        // 段階の合計は、時間のある行が 2 つ以上のときだけ（1 行なら行の時間と同じで重なる）
        const timed = [...tl, ...sys].filter((s) => (s.durationMs ?? 0) > 0).length;
        const total = timed > 1 || Boolean(stop.parallelMs);
        return (
          <Fragment key={stop.key}>
            <section data-stage={stop.key} className={cn(i > 0 && "border-t-[0.5px] border-divider")}>
              <h4 className={cn("m-0 flex items-baseline gap-2 pb-0.5 pt-2", pad)}>
                <span className="eyebrow normal-case tracking-normal">{name(stop)}</span>
                <span className="nums ml-auto pr-[21px] font-mono text-mini text-muted-2 max-md:pr-[19px]">
                  {total && stop.durationMs > 0 && formatMs(stop.durationMs)}
                  {total && stop.parallelMs ? ` ${interpolate(t.chat.flowParallelShort, { ms: formatMs(stop.parallelMs) })}` : ""}
                </span>
              </h4>
              {tools(tl)}
              {system(sys)}
            </section>
            {sent && (
              <div data-sent-line title={t.chat.flowSentHint} className={cn("flex items-center gap-2 py-1.5 text-mini text-muted-2", pad)}>
                <span className="h-px flex-1 border-t border-dashed border-divider-strong" />
                <span className="shrink-0">
                  {t.chat.flowSent} <span className="nums font-mono">{formatMs(durationMs)}</span>
                </span>
                <span className="h-px flex-1 border-t border-dashed border-divider-strong" />
              </div>
            )}
          </Fragment>
        );
      })}
      {rest.length > 0 && (
        <section className={cn(stages.length > 0 && "border-t-[0.5px] border-divider")}>
          {tools(rest.filter((s) => s.name !== "system"))}
          {system(rest.filter((s) => s.name === "system"))}
        </section>
      )}
    </div>
  );
}
