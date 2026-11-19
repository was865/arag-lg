"use client";

import { Fragment, useState } from "react";
import { useReducedMotion } from "motion/react";
import { Segmented } from "@/components/ui/segmented";
import { FlowGraph, type NodeView } from "@/components/chat/graph-view";
import { SentMark, StopMark, detailOf } from "@/components/chat/flow-parts";
import { CardSteps, StageTimeline, StagedSteps } from "@/components/chat/tool-steps/staged";
import type { ToolCall } from "@/lib/types";
import { cn, formatMs } from "@/lib/utils";
import { FLOW_GRAPH, type FlowNodeId, type FlowRoute, type FlowRun, type FlowStop } from "@/lib/chat/flow";
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

/**
 * いつもと違う経路だけをひと言で（流れの見出しの右）。そのまま通過した回答は停留所の印で分かるので何も足さない。
 * 実行中は途中の経路なので言わない（今の段階は見出しの段階の列が示す）。
 */
function summaryOf(r: FlowRoute, running: boolean, t: Dictionary): string | null {
  const c = t.chat;
  if (running) return null;
  if (r.usedDraft) return c.flowSummaryUsedDraft;
  if (r.sentBack > 0) return interpolate(c.flowSummarySentBack, { n: String(r.sentBack) });
  if (r.chat) return c.flowSummaryChat;
  return null;
}
/** 経路の札を書く分岐（いつもと違う経路と、続けて聞くを作らなかった「なし」）。資料・通過・候補ありは書かない */
const UNUSUAL_EDGES = new Set(["chat", "send_back", "retry", "use_draft", "end"]);

/** 段階の説明（make graph が書き出す節点の説明。名前のホバーで読む）。 */
const DESCRIPTION = new Map(FLOW_GRAPH.nodes.map((n) => [n.id, n.description]));

/** 選んでいる鍵（経路の停留所 `investigate-2`、または図の節点 `investigate`）に当たる停留所か */
export function stopPicked(s: FlowStop, selected: string | null | undefined): boolean {
  return Boolean(selected) && (s.key === selected || s.node === selected);
}

function nodeViews(route: FlowRoute, flow: FlowRun, running: boolean, t: Dictionary, canSelect: boolean): NodeView[] {
  return flow.nodes.map((n) => {
    const stops = route.stops.filter((s) => s.node === n.id);
    const ran = stops.filter((s) => !s.notRun);
    const last = stops.at(-1);
    const detail = last ? detailOf(last, t).replace("\n", " ") : "";
    const rounds = ran.map((s) => {
      const head = ran.length > 1 ? `${interpolate(t.chat.flowRound, { n: String(s.round) })}: ` : "";
      const time = s.durationMs > 0 ? `（${formatMs(s.durationMs)}）` : "";
      return `${head}${detailOf(s, t).replace("\n", " ")}${time}`;
    });
    return {
      id: n.id,
      label: n.label,
      passed: n.passed,
      visits: n.visits,
      detail,
      title: [`${n.label} — ${n.description}`, ...rounds].join("\n"),
      usable: canSelect && ran.some((s) => s.stepIds.length > 0),
      current: running && (stops.some((s) => s.current) || (!route.stops.some((s) => s.current) && n.current)),
      notable: stops.some((s) => s.outcome === "sent_back" || s.outcome === "used_draft" || s.outcome === "failed"),
    };
  });
}

type View = "route" | "graph";

/**
 * グラフの実行経路（specs/029 R7・T35）。2 つの見方を同じ見た目（墨の線、朱は送信・選択・実行中だけ）で切り替える。
 * - 経路（既定）: この回答が実際にたどった順。差し戻しの後は「2 周目」と続けて並べ、各段階に何をしたかと時間。
 *   段階の時間の合計が、ほぼ「回答を送信」の時間になる（モデルの応答の時間も記録する。T35）。
 * - グラフ: LangGraph の節点と辺の全体に、通った辺と通らなかった辺を描き分ける。
 * どちらでも段階（節点）を押すと、そこのステップだけに一覧を絞る（R8）。選んだものは切り替えても残る。
 */
export function RunFlow({
  route,
  flow,
  running = false,
  durationMs = 0,
  selected,
  onSelect,
  defaultView = "route",
  steps,
  variant = "card",
  expandedMap = {},
  onToggleStep = () => {},
}: {
  /** ステップの見せ方（利用者の設定）。カード: 経路の下にカード。タイムライン: 経路とステップを 1 本の線に（T38） */
  variant?: "card" | "timeline";
  /** ステップを渡すと、経路とステップを 1 つにして見せる（経路: 停留所の下にステップ、グラフ: 図の下に段階ごとの一覧。T37） */
  steps?: ToolCall[];
  expandedMap?: Record<string, boolean>;
  onToggleStep?: (id: string) => void;
  route: FlowRoute;
  flow: FlowRun;
  /** 最初に見せる見方（既定は経路） */
  defaultView?: View;
  running?: boolean;
  /** run の所要時間（回答を送るまで）。「回答を送信」に添える */
  durationMs?: number;
  /** 絞っている停留所の鍵か節点 */
  selected?: string | null;
  onSelect?: (key: string | null) => void;
}) {
  const { t } = useT();
  const reduced = useReducedMotion();
  const [view, setView] = useState<View>(defaultView);
  const summary = summaryOf(route, running, t);
  const sent = !running && durationMs > 0 && route.stops.some((s) => s.node === "finalize");
  const picked = route.stops.filter((s) => stopPicked(s, selected));
  const name = (s: FlowStop) => (s.round > 1 ? `${s.label}（${interpolate(t.chat.flowRound, { n: String(s.round) })}）` : s.label);
  const pickedName = picked.length === 1 ? name(picked[0]!) : picked[0]?.label;

  const shown = steps && selected ? steps.filter((x) => picked.some((s) => s.stepIds.includes(x.id))) : steps;

  return (
    <div className={cn("@container px-3.5 pb-3 pt-2.5 max-md:px-3", !steps && "border-b-[0.5px] border-divider")}>
      <div className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-caption font-semibold text-muted">{t.chat.flowTitle}</span>
        {summary && <span className="text-caption text-fg-2">{summary}</span>}
        <span className="ml-auto flex items-center gap-2">
          {route.inferred && <span className="text-caption text-muted-2">{t.chat.flowInferred}</span>}
          <Segmented
            label={t.chat.flowTitle}
            value={view}
            options={[
              ["route", t.chat.flowViewRoute],
              ["graph", t.chat.flowViewGraph],
            ]}
            onChange={setView}
          />
        </span>
      </div>
      {view === "route" && steps && variant === "timeline" ? (
        <div className="pt-1">
          <StageTimeline route={route} steps={steps} expandedMap={expandedMap} onToggleStep={onToggleStep} durationMs={durationMs} running={running} t={t} />
        </div>
      ) : view === "route" ? (
        <RouteList route={route} running={running} sent={sent} durationMs={durationMs} selected={selected} onSelect={onSelect} name={name} t={t} />
      ) : (
        <div className="animate-fade-in motion-reduce:animate-none">
          <FlowGraph
            views={nodeViews(route, flow, running, t, Boolean(onSelect))}
            flow={flow}
            sent={sent}
            durationMs={durationMs}
            selected={selected}
            onSelect={onSelect}
            draw={!reduced}
            t={t}
          />
        </div>
      )}
      {pickedName && onSelect && (view === "graph" || !steps || variant === "card") && (
        <div className="mt-2 flex animate-fade-in items-center gap-1.5 text-caption text-muted motion-reduce:animate-none">
          <span>{interpolate(t.chat.flowFiltered, { node: pickedName })}</span>
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
      {shown && (view === "graph" || variant === "card") && (
        <div className="-mx-3.5 -mb-3 mt-2.5 border-t-[0.5px] border-divider max-md:-mx-3">
          {variant === "card" ? (
            <CardSteps route={route} steps={shown} expandedMap={expandedMap} onToggleStep={onToggleStep} durationMs={running ? undefined : durationMs} t={t} />
          ) : (
            <StagedSteps route={route} steps={shown} expandedMap={expandedMap} onToggleStep={onToggleStep} durationMs={running ? undefined : durationMs} t={t} />
          )}
        </div>
      )}
    </div>
  );
}

/** 経路に並べるもの: 停留所と、回答を利用者に送った時点（確定の節点が run.completed を送る。T32） */
type RouteItem = { kind: "stop"; s: FlowStop } | { kind: "sent" };

/**
 * 実際にたどった順の経路。幅があり停留所が 8 つまでなら横一列、狭いか長い経路は縦に並べる。
 * 色はグラフの図と同じ: 線と印は墨、通らなかったもの・送信の後は点線、朱は送信・選択・実行中だけ。
 */
function RouteList({
  route,
  running,
  sent,
  durationMs,
  selected,
  onSelect,
  name,
  t,
}: {
  route: FlowRoute;
  running: boolean;
  sent: boolean;
  durationMs: number;
  selected?: string | null;
  onSelect?: (key: string | null) => void;
  name: (s: FlowStop) => string;
  t: Dictionary;
}) {
  const items: RouteItem[] = [];
  for (const s of route.stops) {
    items.push({ kind: "stop", s });
    if (s.node === "finalize" && sent && !running) items.push({ kind: "sent" });
  }
  const wide = items.length <= 8;
  const row = (cls: string) => (wide ? cls : "");
  return (
    <ol className={cn("m-0 flex list-none flex-col p-0", row("@[480px]:flex-row @[480px]:pt-2"))}>
      {items.map((it, i) => {
        const next = items[i + 1];
        const via = next?.kind === "stop" && next.s.via && UNUSUAL_EDGES.has(next.s.via.key) ? next.s.via : undefined;
        const s = it.kind === "stop" ? it.s : undefined;
        // 次への線。差し戻し・やり直しの後、送信の後、通らなかった節点へは点線
        const line = next && (
          <span
            aria-hidden
            style={{ animationDelay: `${i * 40 + 100}ms` }}
            className={cn(
              "absolute left-[7.5px] top-[19px] bottom-[3px] w-0 animate-draw border-l motion-reduce:animate-none",
              row("@[480px]:bottom-auto @[480px]:left-[calc(50%+11px)] @[480px]:right-[calc(-50%+11px)] @[480px]:top-[7.5px] @[480px]:h-0 @[480px]:w-auto @[480px]:border-l-0 @[480px]:border-t"),
              s?.outcome === "sent_back" || s?.outcome === "retried" || it.kind === "sent" || (next.kind === "stop" && next.s.notRun)
                ? "border-dashed border-divider-strong"
                : "border-muted/60",
            )}
          />
        );
        // 条件つきの辺で選ばれた分岐（縦では線の横、横一列では線の上）
        const edge = via && (
          <span
            data-edge={via.key}
            className={cn(
              "absolute bottom-0.5 left-[22px] z-[1] whitespace-nowrap text-[10px] font-medium leading-none text-fg-2",
              row("@[480px]:bottom-auto @[480px]:left-full @[480px]:top-[-7px] @[480px]:-translate-x-1/2"),
            )}
          >
            {via.label}
          </span>
        );
        const liCls = cn(
          "relative min-w-0 animate-fade-up last:pb-0 motion-reduce:animate-none",
          via ? "pb-5" : "pb-2.5",
          row("@[480px]:flex-1 @[480px]:pb-0"),
        );
        const body = (mark: React.ReactNode, label: React.ReactNode, detail: React.ReactNode, time: React.ReactNode) => (
          <>
            {mark}
            <span className={cn("flex min-w-0 flex-1 items-baseline gap-2", row("@[480px]:w-full @[480px]:flex-col @[480px]:items-center @[480px]:gap-0"))}>
              {label}
              {detail}
              {time}
            </span>
          </>
        );
        const timeCls = cn("nums shrink-0 font-mono text-[10px] text-muted-2", row("@[480px]:mt-0.5"));
        const boxCls = cn(
          "flex w-full min-w-0 items-start gap-2.5",
          row("@[480px]:flex-col @[480px]:items-center @[480px]:gap-1.5 @[480px]:px-1 @[480px]:text-center"),
        );
        if (it.kind === "sent") {
          return (
            <li key="sent" data-sent style={{ animationDelay: `${i * 40}ms` }} className={liCls} title={t.chat.flowSentHint}>
              {line}
              {edge}
              <div className={boxCls}>
                {body(
                  <SentMark />,
                  <span className={cn("shrink-0 text-footnote font-medium text-fg", row("@[480px]:text-caption"))}>{t.chat.flowSent}</span>,
                  null,
                  <span className={timeCls}>{formatMs(durationMs)}</span>,
                )}
              </div>
            </li>
          );
        }
        const st = it.s;
        const detail = detailOf(st, t);
        const active = stopPicked(st, selected);
        const usable = Boolean(onSelect) && st.stepIds.length > 0;
        return (
          <li key={st.key} data-stop={st.key} style={{ animationDelay: `${i * 40}ms` }} className={liCls}>
            {line}
            {edge}
            <button
              type="button"
              disabled={!usable}
              aria-pressed={active}
              onClick={() => onSelect?.(active ? null : st.key)}
              className={cn(
                "group rounded-control border-0 bg-transparent p-0 text-left outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
                boxCls,
                usable ? "cursor-pointer" : "cursor-default",
                st.notRun && "opacity-60",
              )}
            >
              {body(
                <span className={cn("rounded-full transition-shadow duration-(--duration-mid)", active && "ring-[3px] ring-accent/25")}>
                  <StopMark s={st} />
                </span>,
                <span
                  title={DESCRIPTION.get(st.node)}
                  className={cn(
                    "shrink-0 text-footnote font-medium transition-colors duration-(--duration-mid)",
                    active || st.current ? "text-accent" : "text-fg",
                    usable && "group-hover:text-accent",
                    row("@[480px]:max-w-full @[480px]:truncate @[480px]:text-caption"),
                  )}
                >
                  {name(st)}
                </span>,
                <span
                  className={cn(
                    "min-w-0 flex-1 truncate text-caption",
                    st.outcome === "sent_back" || st.outcome === "used_draft" ? "text-fg-2" : "text-muted",
                    st.outcome === "failed" && "text-danger",
                    row("@[480px]:line-clamp-2 @[480px]:w-full @[480px]:flex-none @[480px]:whitespace-pre-line @[480px]:leading-snug"),
                  )}
                  title={detail.replace("\n", " ")}
                >
                  {detail}
                </span>,
                st.durationMs > 0 ? (
                  <span
                    className={timeCls}
                    title={st.parallelMs ? interpolate(t.chat.flowParallel, { ms: formatMs(st.parallelMs) }) : undefined}
                  >
                    {formatMs(st.durationMs)}
                    {st.parallelMs ? <span className="text-muted-2/70"> {interpolate(t.chat.flowParallelShort, { ms: formatMs(st.parallelMs) })}</span> : null}
                  </span>
                ) : null,
              )}
            </button>
          </li>
        );
      })}
    </ol>
  );
}
