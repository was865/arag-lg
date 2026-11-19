"use client";

import { cn, formatMs } from "@/lib/utils";
import type { FlowNodeId, FlowRun } from "@/lib/chat/flow";
import { LAYOUT, graphLayout, type GraphLayout } from "@/lib/chat/graph-layout";
import type { Dictionary } from "@/i18n/dictionary";

/** 札を書く分岐（いつもと違う経路）。資料・通過・候補ありはいつもの経路なので書かない */
const UNUSUAL_EDGES = new Set(["chat", "send_back", "retry", "use_draft", "clarify"]);

/** 図に描く 1 つの節点の中身（経路の停留所を節点ごとにまとめたもの） */
export interface NodeView {
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

/**
 * グラフの構造の図（specs/029 T35）。節点を定義の順に 1 本の線に並べ、通った辺を墨の実線、通らなかった辺を淡い点線で描く。
 * 広い所は横（弧は上）、狭い所は同じ図を縦（弧は左）に。朱は送信の点・選んだ節点・実行中の節点だけ。
 */
export function FlowGraph(props: Omit<GraphProps, "layout">) {
  return (
    <>
      <div className="hidden @[620px]:block">
        <Graph layout={graphLayout("row")} {...props} />
      </div>
      <div className="@[620px]:hidden">
        <Graph layout={graphLayout("column")} {...props} />
      </div>
    </>
  );
}

interface GraphProps {
  layout: GraphLayout;
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

function Graph({ layout, views, flow, sent, durationMs, selected, onSelect, draw, t }: GraphProps) {
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
            {t.chat.flowSentShort} <tspan className="font-mono">{formatMs(durationMs)}</tspan>
          </text>
        </g>
      )}

      {/* 節点 */}
      {views.map((v) => {
        const p = pos.get(v.id)!;
        // 経路の停留所（investigate-2 など）を選んでいるときも、その節点を選んだものとして見せる
        const active = selected === v.id || Boolean(selected?.startsWith(`${v.id}-`));
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

