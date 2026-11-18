"use client";

import { Fragment } from "react";
import { useReducedMotion } from "motion/react";
import { cn, formatMs } from "@/lib/utils";
import type { FlowNodeId, FlowRoute, FlowRun, FlowStop } from "@/lib/chat/flow";
import { LAYOUT, graphLayout, type GraphLayout } from "@/lib/chat/graph-layout";
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
      if (s.notRun) return c.flowFollowupsOff;
      const q = (s.steps.at(-1)?.output as Record<string, unknown> | null | undefined)?.questions;
      return Array.isArray(q) ? interpolate(c.flowFollowups, { n: String(q.length) }) : (s.steps.at(-1)?.summary ?? "");
    }
    default:
      return s.steps.at(-1)?.summary ?? "";
  }
}

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

/** 札を書く分岐（いつもと違う経路）。資料・通過・候補ありはいつもの経路なので書かない */
const UNUSUAL_EDGES = new Set(["chat", "send_back", "retry", "use_draft"]);

/** 図に描く 1 つの節点の中身（経路の停留所を節点ごとにまとめたもの） */
interface NodeView {
  id: FlowNodeId;
  label: string;
  passed: boolean;
  visits: number;
  /** 名前の下（縦は横）に出す 1 行。周回があるときは最後の周回 */
  detail: string;
  /** ホバーで読む説明・周回ごとの内訳・時間 */
  title: string;
  /** 押すとこの節点のステップに絞れる */
  usable: boolean;
  current: boolean;
  /** 差し戻し・失敗など、目を留めてほしい節点 */
  notable: boolean;
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

/**
 * グラフの実行経路（specs/029 R7・T34）。グラフの節点を定義の順に 1 本の線に並べ、この回答が通った辺を墨の実線、
 * 通らなかった辺を淡い点線で描く。いつも通る回答は 1 本の線に見え、差し戻し・雑談などのときだけ弧が実線になる。
 * 節点の下に何をしたかを 1 行、ホバーで説明と周回ごとの内訳を出す。確定の後に「送信」と所要時間の印を置く。
 * 節点を押すと、その節点のステップだけに一覧を絞る（R8）。広い所は横、狭い所は縦に描く（同じ図）。
 * 朱は送信の印・選んだ節点・実行中の節点だけに使う。動きは開いたときに線を一度描くだけ。
 */
export function RunFlow({
  route,
  flow,
  running = false,
  durationMs = 0,
  selected,
  onSelect,
}: {
  route: FlowRoute;
  flow: FlowRun;
  running?: boolean;
  /** run の所要時間（回答を送るまで）。「送信」に添える */
  durationMs?: number;
  /** 絞っている節点 */
  selected?: string | null;
  onSelect?: (node: string | null) => void;
}) {
  const { t } = useT();
  const reduced = useReducedMotion();
  const summary = summaryOf(route, running, t);
  const views = nodeViews(route, flow, running, t, Boolean(onSelect));
  const picked = views.find((v) => v.id === selected);
  const sent = !running && durationMs > 0 && flow.nodes.some((n) => n.id === "finalize" && n.passed);
  const props: GraphProps = { views, flow, sent, durationMs, selected, onSelect, draw: !reduced, t };

  return (
    <div className="@container border-b-[0.5px] border-divider px-3.5 pb-2.5 pt-2.5 max-md:px-3">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span className="text-caption font-semibold text-muted">{t.chat.flowTitle}</span>
        {summary && <span className="text-caption text-fg-2">{summary}</span>}
        {route.inferred && <span className="ml-auto text-caption text-muted-2">{t.chat.flowInferred}</span>}
      </div>
      {/* 同じ図を、広い所は横・狭い所は縦に（片方だけ見せる） */}
      <div className="hidden @[620px]:block">
        <Graph layout={graphLayout("row")} {...props} />
      </div>
      <div className="@[620px]:hidden">
        <Graph layout={graphLayout("column")} {...props} />
      </div>
      {picked && onSelect && (
        <div className="mt-1 flex animate-fade-in items-center gap-1.5 text-caption text-muted motion-reduce:animate-none">
          <span>{interpolate(t.chat.flowFiltered, { node: picked.label })}</span>
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

interface GraphProps {
  views: NodeView[];
  flow: FlowRun;
  sent: boolean;
  durationMs: number;
  selected?: string | null;
  onSelect?: (node: string | null) => void;
  /** 開いたときに通った辺を一度描く（動きを減らす設定では描かない） */
  draw: boolean;
  t: Dictionary;
}

/** 文字の量を図の幅に収める（全角 1・半角 0.5 で数える） */
function clip(s: string, max: number): string {
  let w = 0;
  for (let i = 0; i < s.length; i++) {
    w += s.charCodeAt(i) < 0x100 ? 0.5 : 1;
    if (w > max) return `${s.slice(0, i)}…`;
  }
  return s;
}

function Graph({ layout, views, flow, sent, durationMs, selected, onSelect, draw, t }: GraphProps & { layout: GraphLayout }) {
  const row = layout.orient === "row";
  const R = LAYOUT.R;
  const edgeRun = new Map(flow.edges.map((e) => [`${e.source}-${e.target}`, e]));
  const pos = new Map(layout.nodes.map((n) => [n.id, n]));
  const fin = pos.get("finalize")!;
  const fu = pos.get("followups")!;
  // 送信の印: 確定 → 続けて聞くの辺の中ほど
  const sx = (fin.x + fu.x) / 2;
  const sy = (fin.y + fu.y) / 2;

  return (
    <svg
      viewBox={`0 0 ${layout.width} ${layout.height}`}
      width={row ? "100%" : layout.width}
      height={row ? undefined : layout.height}
      data-orient={layout.orient}
      role="group"
      aria-label={t.chat.flowTitle}
      className={cn("block select-none", row ? "w-full" : "max-w-full")}
    >
      {/* 辺 */}
      {layout.edges.map((g, i) => {
        const run = edgeRun.get(g.id);
        const taken = Boolean(run?.passed);
        const key = g.edge.key ?? "";
        const label = taken && UNUSUAL_EDGES.has(key) ? `${g.edge.label}${g.edge.kind === "back" && run ? ` ×${run.count}` : ""}` : null;
        return (
          <g key={g.id} data-edge={key || g.id} data-taken={taken ? "1" : "0"}>
            <title>{[g.edge.label, taken ? (run && run.count > 1 ? `×${run.count}` : "") : t.chat.flowNotPassed].filter(Boolean).join(" ")}</title>
            <path
              d={g.d}
              fill="none"
              strokeLinecap="round"
              strokeWidth={taken ? 1.3 : 1}
              strokeDasharray={taken ? (draw ? 1 : undefined) : "2.5 3"}
              pathLength={taken && draw ? 1 : undefined}
              className={taken ? "stroke-muted" : "stroke-divider-strong"}
              style={taken && draw ? { animation: `ar-trace 0.4s var(--ease-out) ${i * 0.03}s both` } : undefined}
            />
            {/* 矢印は通った辺だけ（通らなかった辺は点線で十分） */}
            {taken && g.arc && <ArrowAt d={g.d} />}
            {label && (
              <text
                x={g.lx}
                y={g.ly + 3.5}
                textAnchor="middle"
                paintOrder="stroke"
                strokeWidth={4}
                strokeLinejoin="round"
                className="stroke-surface-2 fill-fg-2 text-[10px] font-medium"
                style={draw ? { animation: `ar-overlay-in 0.3s ease-out 0.3s both` } : undefined}
              >
                {label}
              </text>
            )}
          </g>
        );
      })}

      {/* 送信の印（ここで回答を送った。朱は送信に使う色） */}
      {sent && (
        <g data-sent>
          <title>{t.chat.flowSentHint}</title>
          <circle cx={sx} cy={sy} r={2.6} className="fill-accent" />
          <text
            x={row ? sx : sx + 10}
            y={row ? sy - 7 : sy + 3.5}
            textAnchor={row ? "middle" : "start"}
            className="fill-muted text-[10px]"
          >
            {t.chat.flowSent} <tspan className="font-mono">{formatMs(durationMs)}</tspan>
          </text>
        </g>
      )}

      {/* 節点 */}
      {views.map((v) => {
        const p = pos.get(v.id)!;
        const active = selected === v.id;
        const select = () => onSelect?.(active ? null : v.id);
        return (
          <g
            key={v.id}
            data-node={v.id}
            role={v.usable ? "button" : undefined}
            tabIndex={v.usable ? 0 : undefined}
            aria-pressed={v.usable ? active : undefined}
            aria-label={`${v.label} ${v.detail}`.trim()}
            onClick={v.usable ? select : undefined}
            onKeyDown={
              v.usable
                ? (e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      select();
                    }
                  }
                : undefined
            }
            className={cn("group outline-none", v.usable ? "cursor-pointer" : "cursor-default")}
          >
            <title>{v.title}</title>
            {/* 押せる範囲（文字まで含める） */}
            <rect
              x={row ? p.x - 40 : p.x - 10}
              y={row ? p.y - 10 : p.y - 12}
              width={row ? 80 : layout.width - p.x + 10}
              height={row ? 44 : 24}
              className="fill-transparent"
            />
            {(active || v.current) && (
              <circle
                cx={p.x}
                cy={p.y}
                r={R + 4}
                strokeWidth={1.5}
                className={cn("fill-none stroke-accent/45", v.current && "animate-breathe motion-reduce:animate-none")}
              />
            )}
            {v.passed ? (
              <circle cx={p.x} cy={p.y} r={R} className={cn(v.current ? "fill-accent" : "fill-muted", "group-hover:fill-fg group-focus-visible:fill-fg")} />
            ) : (
              <circle cx={p.x} cy={p.y} r={R - 0.5} strokeWidth={1} strokeDasharray="2 2" className="fill-surface-2 stroke-divider-strong" />
            )}
            <text
              x={row ? p.x : p.x + 14}
              y={row ? p.y + 19 : p.y + 4}
              textAnchor={row ? "middle" : "start"}
              className={cn(
                "text-[11.5px] font-medium",
                active ? "fill-accent" : v.passed ? "fill-fg" : "fill-muted-2",
                v.usable && !active && "group-hover:fill-accent",
              )}
            >
              {v.label}
              {v.visits > 1 && (
                <tspan dx={2} className="fill-muted font-mono text-[10px] font-normal">
                  ×{v.visits}
                </tspan>
              )}
              {!row && v.detail && (
                <tspan dx={8} className={cn("text-[10.5px] font-normal", v.notable ? "fill-fg-2" : "fill-muted")}>
                  {clip(v.detail, 18)}
                </tspan>
              )}
            </text>
            {row && v.detail && (
              <text
                x={p.x}
                y={p.y + 32}
                textAnchor="middle"
                className={cn("text-[10px]", v.notable ? "fill-fg-2" : "fill-muted")}
              >
                {clip(v.detail, 8)}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

/** 弧の終わりの小さな矢印（パスの最後の向きに合わせる。終わりの 2 点はパスの末尾から読む） */
function ArrowAt({ d }: { d: string }) {
  const nums = d.match(/-?\d+(\.\d+)?/g)?.map(Number) ?? [];
  const [cx, cy, ex, ey] = nums.slice(-4) as [number, number, number, number];
  const a = Math.atan2(ey - cy, ex - cx);
  const s = 4;
  const p = (da: number) => `${ex - s * Math.cos(a + da)} ${ey - s * Math.sin(a + da)}`;
  return <path d={`M ${p(0.5)} L ${ex} ${ey} L ${p(-0.5)}`} fill="none" strokeWidth={1.2} strokeLinecap="round" strokeLinejoin="round" className="stroke-muted" />;
}
