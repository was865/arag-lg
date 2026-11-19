"use client";

/**
 * 段階ごとのステップ（specs/029 T36・T37）。経路の見方では StageTimeline（停留所の下にステップ）、
 * グラフの見方では StagedSteps（図の下に、左の細い列に段階の名前）を使う。
 * 左の細い列に段階の名前、右に行（エージェントのステップ → その段階のシステムの処理を淡く）。段階の間は線でなく余白で区切る。
 * 済みの印（✓）は出さない（ほとんどが済みで、上の経路が示す）。実行中・失敗のときだけ印を出す。
 * 時間は右の 1 列。段階の時間は上の経路に出ているので、ここでは行の時間だけ。確定の後に「回答を送信」の区切り。
 */
import { Fragment } from "react";
import { SearchDetail, searchHits } from "@/components/chat/search-detail";
import { cn, formatMs } from "@/lib/utils";
import type { ToolCall } from "@/lib/types";
import type { FlowRoute, FlowStop } from "@/lib/chat/flow";
import type { Dictionary } from "@/i18n/dictionary";
import { interpolate } from "@/i18n/interpolate";
import { AutoBadge, StatusIcon, TOOL_ICONS, hasInputData, inputSectionLabel, isBySystem, isExpandable, outputSectionLabel, sectionLabelCls, stepDurationLabel } from "./shared";
import { ToolInputBlock } from "./step-input";
import { ToolOutputBlock } from "./step-output";
import { PurposeNote, SubSteps, groupSteps } from "./index";
import { FLOW_GRAPH } from "@/lib/chat/flow";
import { SentMark, StopMark, detailOf } from "@/components/chat/flow-parts";

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

/** 1 行。エージェントのステップは濃く、システムの処理は小さく淡く。押すと中身（入力・出力・検索の明細）を開く。 */
function StageRow({
  step,
  kids,
  expanded,
  onToggle,
  expandedMap,
  onToggleStep,
  hideTime = false,
  t,
}: {
  step: ToolCall;
  kids?: ToolCall[];
  /** 段階の見出しが同じ時間を出しているとき（段階に時間のある行が 1 つだけ） */
  hideTime?: boolean;
  expanded: boolean;
  onToggle: () => void;
  expandedMap: Record<string, boolean>;
  onToggleStep: (id: string) => void;
  t: Dictionary;
}) {
  const system = step.name === "system";
  const hasKids = Boolean(kids?.length);
  const expandable = hasKids || isExpandable(step);
  const hits = !hasKids ? searchHits(step) : null;
  const time = hideTime ? null : stepDurationLabel(step);
  const mark = step.status === "running" || step.status === "error" || step.status === "pending";
  return (
    <div data-step={step.id} data-system={system ? "1" : undefined}>
      <button
        type="button"
        onClick={expandable ? onToggle : undefined}
        aria-expanded={expandable ? expanded : undefined}
        title={step.label ? step.name : undefined}
        className={cn(
          "grid w-full grid-cols-[16px_auto_minmax(0,1fr)_auto_11px] items-center gap-x-2.5 rounded-control border-0 bg-transparent px-1.5 text-left outline-none",
          "transition-colors duration-(--duration-fast) focus-visible:ring-2 focus-visible:ring-accent/50",
          "py-[3px]",
          expandable ? "cursor-pointer hover:bg-surface" : "cursor-default",
          expanded && "bg-surface",
        )}
      >
        {mark ? (
          <StatusIcon status={step.status} t={t} name={step.name} />
        ) : (
          <span className={cn("grid place-items-center", system ? "text-muted-2" : "text-muted")}>
            <svg viewBox="0 0 16 16" width={system ? 11 : 12} height={system ? 11 : 12} aria-hidden>
              {TOOL_ICONS[step.name]}
            </svg>
          </span>
        )}
        <span className={cn("inline-flex min-w-0 items-center gap-1.5 text-caption", system ? "text-muted" : "font-medium text-fg-2")}>
          <span className="truncate">{step.label || step.name}</span>
          {isBySystem(step) && <AutoBadge t={t} />}
        </span>
        <span className="min-w-0 truncate text-caption text-muted max-md:hidden">{step.summary}</span>
        <span className="nums font-mono text-mini tabular-nums text-muted-2">{time}</span>
        {expandable ? (
          <span className={cn("text-muted-2 transition-transform duration-(--duration-fast)", expanded && "rotate-180")}>
            <svg viewBox="0 0 16 16" width="11" height="11" aria-hidden>
              <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        ) : (
          <span aria-hidden />
        )}
      </button>
      {expandable && expanded && (
        <div className="mb-1.5 ml-[32px] mt-0.5 flex animate-fade-up flex-col gap-2.5 motion-reduce:animate-none max-md:ml-1.5">
          {/* 狭い画面では行に出ない要約をここで */}
          {step.summary && <div className="hidden text-caption text-muted max-md:block">{step.summary}</div>}
          {hasKids ? (
            <div>
              <PurposeNote step={step} />
              <SubSteps steps={kids} expandedMap={expandedMap} onToggleStep={onToggleStep} t={t} />
            </div>
          ) : hits ? (
            <SearchDetail step={step} hits={hits} />
          ) : (
            <>
              {hasInputData(step.input) && (
                <div>
                  <div className={sectionLabelCls}>{inputSectionLabel(step, t)}</div>
                  <ToolInputBlock step={step} t={t} />
                </div>
              )}
              {step.output != null && (
                <div>
                  <div className={sectionLabelCls}>{outputSectionLabel(step, t)}</div>
                  <ToolOutputBlock step={step} t={t} />
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function StagedSteps({
  route,
  steps,
  expandedMap,
  onToggleStep,
  durationMs,
  t,
}: {
  route: FlowRoute;
  steps: ToolCall[];
  expandedMap: Record<string, boolean>;
  onToggleStep: (id: string) => void;
  /** 回答を送るまでの時間（「回答を送信」の区切りに添える） */
  durationMs?: number;
  t: Dictionary;
}) {
  const { childrenOf } = groupSteps(steps);
  const { stages, rest } = stagesOf(route, steps);
  const name = (s: FlowStop) => (s.round > 1 ? `${s.label}（${interpolate(t.chat.flowRound, { n: String(s.round) })}）` : s.label);
  const rows = (list: ToolCall[]) =>
    list.map((s) => (
      <StageRow
        key={s.id}
        step={s}
        kids={childrenOf.get(s.id)}
        expanded={!!expandedMap[s.id]}
        onToggle={() => onToggleStep(s.id)}
        expandedMap={expandedMap}
        onToggleStep={onToggleStep}
        t={t}
      />
    ));
  const stage = (key: string, label: string | null, list: ToolCall[], current = false) => (
    <section
      key={key}
      data-stage={key}
      className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-x-2 py-1 max-md:grid-cols-1"
    >
      <h4
        className={cn(
          "m-0 pt-[4px] text-caption font-normal leading-snug max-md:pb-0.5 max-md:pl-1.5 max-md:pt-1",
          current ? "text-fg" : "text-muted-2",
        )}
      >
        {label}
      </h4>
      <div className="flex min-w-0 flex-col">{rows(list)}</div>
    </section>
  );

  return (
    <div className="flex flex-col px-2 py-1.5 max-md:px-1.5">
      {stages.map(({ stop, tools, system }) => (
        <Fragment key={stop.key}>
          {stage(stop.key, name(stop), [...tools, ...system], stop.current)}
          {stop.node === "finalize" && durationMs && durationMs > 0 ? (
            <div
              data-sent-line
              title={t.chat.flowSentHint}
              className="my-1 flex items-center gap-2.5 pl-1.5 pr-1.5 text-mini text-muted-2"
            >
              <span className="h-0 flex-1 border-t border-dashed border-divider-strong" />
              <span className="shrink-0">
                {t.chat.flowSent} <span className="nums font-mono">{formatMs(durationMs)}</span>
              </span>
              <span className="h-0 w-6 border-t border-dashed border-divider-strong" />
            </div>
          ) : null}
        </Fragment>
      ))}
      {rest.length > 0 && stage("rest", null, [...rest.filter((s) => s.name !== "system"), ...rest.filter((s) => s.name === "system")])}
    </div>
  );
}

/** 経路の札を書く分岐（いつもと違う経路と、続けて聞くを作らなかった「なし」） */
const UNUSUAL_EDGES = new Set(["chat", "send_back", "retry", "use_draft", "end"]);
const DESCRIPTION = new Map(FLOW_GRAPH.nodes.map((n) => [n.id, n.description]));

/**
 * 経路とステップを 1 本の時間線に（specs/029 T37）。停留所（印・名前・何をしたか・段階の時間）の下に、
 * その段階のステップを並べる。経路とステップの一覧を別々に並べると同じ順が 2 度出るので、1 つにする。
 * 時間: 段階の時間は見出しに。段階の中に時間のある行が 2 つ以上あるときだけ、行にも時間を出す（重ねない）。
 */
export function StageTimeline({
  route,
  steps,
  expandedMap,
  onToggleStep,
  durationMs,
  running = false,
  t,
}: {
  route: FlowRoute;
  steps: ToolCall[];
  expandedMap: Record<string, boolean>;
  onToggleStep: (id: string) => void;
  durationMs?: number;
  running?: boolean;
  t: Dictionary;
}) {
  const { childrenOf } = groupSteps(steps);
  const roots = steps.filter((s) => !s.parentId);
  type Item = { kind: "stop"; s: FlowStop; rows: ToolCall[] } | { kind: "sent" };
  const items: Item[] = [];
  const used = new Set<string>();
  for (const s of route.stops) {
    const ids = new Set(s.stepIds);
    const own = roots.filter((x) => ids.has(x.id) && !used.has(x.id));
    own.forEach((x) => used.add(x.id));
    // エージェントのステップを先に、その段階のシステムの処理を後に
    items.push({ kind: "stop", s, rows: [...own.filter((x) => x.name !== "system"), ...own.filter((x) => x.name === "system")] });
    if (s.node === "finalize" && !running && durationMs && durationMs > 0) items.push({ kind: "sent" });
  }
  const rest = roots.filter((x) => !used.has(x.id));
  const name = (s: FlowStop) => (s.round > 1 ? `${s.label}（${interpolate(t.chat.flowRound, { n: String(s.round) })}）` : s.label);
  const time = "nums ml-auto shrink-0 pl-2 pr-[27px] font-mono text-mini text-muted-2 max-md:pr-[27px]";

  return (
    <ol className="m-0 flex list-none flex-col p-0">
      {items.map((it, i) => {
        const next = items[i + 1];
        const via = next?.kind === "stop" && next.s.via && UNUSUAL_EDGES.has(next.s.via.key) ? next.s.via : undefined;
        const s = it.kind === "stop" ? it.s : undefined;
        const dashed =
          s?.outcome === "sent_back" || s?.outcome === "retried" || it.kind === "sent" || (next?.kind === "stop" && next.s.notRun);
        // 段階をつなぐ縦の線（印の中心から次の印まで）
        const line = next && (
          <span
            aria-hidden
            className={cn("absolute bottom-[-4px] left-[7.5px] top-[18px] w-0 border-l", dashed ? "border-dashed border-divider-strong" : "border-divider-strong")}
          />
        );
        const edge = via && (
          <div data-edge={via.key} className="relative z-[1] pb-1 pl-[26px] text-mini font-medium leading-none text-fg-2">
            {via.label}
          </div>
        );
        if (it.kind === "sent")
          return (
            <li key="sent" data-sent className="relative pb-2" title={t.chat.flowSentHint}>
              {line}
              <div className="flex items-center gap-2.5">
                <SentMark />
                <span className="text-footnote font-medium text-fg">{t.chat.flowSent}</span>
                <span className={time}>{formatMs(durationMs ?? 0)}</span>
              </div>
              {edge && <div className="pt-1.5">{edge}</div>}
            </li>
          );
        const st = it.s;
        const detail = detailOf(st, t).replace("\n", " ");
        const timed = it.rows.filter((x) => (x.durationMs ?? 0) > 0).length;
        return (
          <li key={st.key} data-stop={st.key} className={cn("relative", via ? "pb-1.5" : "pb-2")}>
            {line}
            <div className={cn("flex min-w-0 items-center gap-2.5", st.notRun && "opacity-60")}>
              <StopMark s={st} />
              <span title={DESCRIPTION.get(st.node)} className={cn("shrink-0 text-footnote font-semibold", st.current ? "text-accent" : "text-fg")}>
                {name(st)}
              </span>
              <span
                className={cn(
                  "min-w-0 truncate text-caption",
                  st.outcome === "sent_back" || st.outcome === "used_draft" ? "text-fg-2" : "text-muted",
                  st.outcome === "failed" && "text-danger",
                )}
              >
                {detail}
              </span>
              <span className={time}>
                {st.durationMs > 0 && formatMs(st.durationMs)}
                {st.parallelMs ? ` ${interpolate(t.chat.flowParallelShort, { ms: formatMs(st.parallelMs) })}` : ""}
              </span>
            </div>
            {it.rows.length > 0 && (
              <div className="ml-[18px] mt-0.5 flex flex-col">
                {it.rows.map((x) => (
                  <StageRow
                    key={x.id}
                    step={x}
                    kids={childrenOf.get(x.id)}
                    expanded={!!expandedMap[x.id]}
                    onToggle={() => onToggleStep(x.id)}
                    expandedMap={expandedMap}
                    onToggleStep={onToggleStep}
                    hideTime={timed < 2}
                    t={t}
                  />
                ))}
              </div>
            )}
            {edge && <div className="pt-1">{edge}</div>}
          </li>
        );
      })}
      {rest.length > 0 && (
        <li className="ml-[18px] flex flex-col">
          {rest.map((x) => (
            <StageRow key={x.id} step={x} kids={childrenOf.get(x.id)} expanded={!!expandedMap[x.id]} onToggle={() => onToggleStep(x.id)} expandedMap={expandedMap} onToggleStep={onToggleStep} t={t} />
          ))}
        </li>
      )}
    </ol>
  );
}

