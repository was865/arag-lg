"use client";

import { useId, useMemo, useState } from "react";
import { useReducedMotion } from "motion/react";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/icons";
import { cn, formatMs } from "@/lib/utils";
import type { FlowNodeId, FlowRoute, FlowRun } from "@/lib/chat/flow";
import { G, graphLayout, replayOf, type EdgeGeom } from "@/lib/chat/graph-layout";
import { useT } from "@/i18n/context";

/** たどり直しを始めるまでの間（開いた直後の描き出しと重ならないように） */
const LEAD = 0.25;

/** SVG の要素を自分の中心で拡大・縮小する */
const SELF_CENTER = { transformBox: "fill-box", transformOrigin: "center" } as const;

/**
 * グラフ全体の弧線図（specs/029 T33）。節点を定義の順に 1 本の線に並べ、飛ばす辺・戻る辺は上の弧にする。
 * 通った辺は朱の実線、通らなかった辺は淡い点線。開くと、この回答がたどった順にトークンが節点を通り、
 * 通った節点が灯り、通った辺が描かれる（「もう一度たどる」でやり直せる。動きを減らす設定では動かさない）。
 * 節点にカーソルを置くと、その節点につながる辺と節点だけを残して、ほかを淡くする。
 */
export function GraphView({ flow, route }: { flow: FlowRun; route: FlowRoute }) {
  const { t } = useT();
  const reduced = useReducedMotion();
  const [play, setPlay] = useState(0);
  const [hover, setHover] = useState<FlowNodeId | null>(null);
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const { nodes, edges } = useMemo(() => graphLayout(), []);
  const replay = useMemo(() => replayOf(route), [route]);
  const nodeRun = new Map(flow.nodes.map((n) => [n.id, n]));
  const edgeRun = new Map(flow.edges.map((e) => [`${e.source}-${e.target}`, e]));
  const animate = !reduced && replay !== null;

  const touches = (g: EdgeGeom, id: FlowNodeId) => g.edge.source === id || g.edge.target === id;
  const edgeNear = (g: EdgeGeom) => !hover || touches(g, hover);
  const nodeNear = (id: FlowNodeId) => !hover || id === hover || edges.some((g) => touches(g, hover) && touches(g, id));
  const marker = (taken: boolean) => `url(#${uid}-${taken ? "on" : "off"})`;

  return (
    <div className="flex flex-col gap-2">
      <div className="-mx-1 overflow-x-auto px-1">
        <svg
          key={play}
          viewBox={`0 0 ${G.W} ${G.H}`}
          role="img"
          aria-label={t.chat.flowViewGraph}
          className="block w-full min-w-[600px] select-none"
        >
          <defs>
            {(["on", "off"] as const).map((k) => (
              <marker key={k} id={`${uid}-${k}`} viewBox="0 0 8 8" refX="6" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M1 1.2L6.5 4 1 6.8z" className={k === "on" ? "fill-accent" : "fill-divider-strong"} />
              </marker>
            ))}
          </defs>

          {/* 辺（節点の下に描く） */}
          {edges.map((g) => {
            const run = edgeRun.get(g.id);
            const taken = Boolean(run?.passed);
            const at = replay?.edgeAt.get(g.id);
            const back = g.edge.kind === "back";
            const trace = taken && animate && at;
            return (
              <g
                key={g.id}
                data-edge={g.edge.key ?? g.id}
                data-taken={taken ? "1" : "0"}
                style={{
                  // 通った辺は、トークンが通り始めるときに現れる。通らなかった辺は最初から淡く出す
                  // （現れる動きは外の g、カーソルで淡くするのは中の g。動きの fill が opacity を上書きするので分ける）
                  animation: trace
                    ? `ar-overlay-in 0.12s ease-out ${LEAD + at.start}s both`
                    : animate
                      ? "ar-overlay-in 0.4s ease-out both"
                      : undefined,
                }}
              >
                <g className="transition-opacity duration-(--duration-mid)" style={{ opacity: edgeNear(g) ? 1 : 0.12 }}>
                <path
                  d={g.d}
                  fill="none"
                  pathLength={trace ? 1 : undefined}
                  strokeLinecap="round"
                  strokeWidth={taken ? 1.6 : 1}
                  strokeDasharray={taken ? (trace ? 1 : undefined) : "3 3"}
                  markerEnd={marker(taken)}
                  className={taken ? "stroke-accent" : "stroke-divider-strong"}
                  style={trace ? { animation: `ar-trace ${at.dur}s linear ${LEAD + at.start}s both` } : undefined}
                />
                {g.edge.label && (
                  <text
                    x={g.lx}
                    y={g.arc ? g.ly + 3.5 : g.ly}
                    textAnchor="middle"
                    paintOrder="stroke"
                    strokeWidth={4}
                    strokeLinejoin="round"
                    className={cn(
                      "stroke-surface-2 font-mono text-[10px]",
                      taken ? (back ? "fill-accent" : "fill-fg-2") : "fill-muted-2",
                    )}
                  >
                    {g.edge.label}
                    {taken && run && back ? ` ×${run.count}` : ""}
                  </text>
                )}
                </g>
              </g>
            );
          })}

          {/* 節点 */}
          {nodes.map((n, i) => {
            const run = nodeRun.get(n.id);
            const passed = Boolean(run?.passed);
            const at = replay?.nodeAt.get(n.id);
            const light = passed && animate && at !== undefined;
            const delay = `${LEAD + (at ?? 0)}s`;
            return (
              <g
                key={n.id}
                tabIndex={0}
                aria-label={`${run?.label ?? n.id}: ${passed ? t.chat.flowPassedNode : t.chat.flowNotPassed}`}
                onMouseEnter={() => setHover(n.id)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(n.id)}
                onBlur={() => setHover(null)}
                className="cursor-default outline-none"
                style={{ animation: !light && animate ? `ar-overlay-in 0.3s ease-out ${i * 0.03}s both` : undefined }}
              >
                <g className="transition-opacity duration-(--duration-mid)" style={{ opacity: nodeNear(n.id) ? 1 : 0.3 }}>
                <title>{run ? `${run.label} — ${run.description}` : n.id}</title>
                {light && (
                  <circle
                    cx={n.x}
                    cy={G.Y}
                    r={G.R}
                    className="fill-accent/40"
                    style={{ ...SELF_CENTER, opacity: 0, animation: `ar-ripple 0.7s ease-out ${delay} both` }}
                  />
                )}
                <g style={light ? { ...SELF_CENTER, animation: `ar-node-on 0.45s var(--ease-spring) ${delay} both` } : undefined}>
                  {passed ? (
                    <>
                      <circle cx={n.x} cy={G.Y} r={G.R} strokeWidth={1.5} className="fill-surface stroke-accent/60" />
                      <circle cx={n.x} cy={G.Y} r={3.2} className="fill-accent" />
                    </>
                  ) : (
                    <circle cx={n.x} cy={G.Y} r={G.R} strokeWidth={1.2} strokeDasharray="2 2" className="fill-surface-2 stroke-divider-strong" />
                  )}
                </g>
                <text
                  x={n.x}
                  y={G.Y + 25}
                  textAnchor="middle"
                  className={cn("text-[12px] font-medium", passed ? "fill-fg" : "fill-muted-2")}
                >
                  {run?.label ?? n.id}
                  {/* 何度も通った節点（差し戻し・やり直し） */}
                  {run && run.visits > 1 && (
                    <tspan dx={3} className="fill-accent font-mono text-[10px] font-semibold">
                      ×{run.visits}
                    </tspan>
                  )}
                </text>
                <text x={n.x} y={G.Y + 40} textAnchor="middle" className="fill-muted-2 font-mono text-[10px]">
                  {passed ? (run && run.durationMs > 0 ? formatMs(run.durationMs) : "") : t.chat.flowNotPassed}
                </text>
                </g>
              </g>
            );
          })}

          {/* たどり直しのトークン（節点の中心をつなぐ道を一定の速さで進み、着いたら消える） */}
          {animate && replay && (
            <g
              aria-hidden
              style={{
                animation: `ar-overlay-in 0.15s ease-out ${LEAD}s both, ar-overlay-out 0.5s ease-in ${LEAD + replay.total + 0.15}s forwards`,
              }}
            >
              {[
                [9, "fill-accent/20"],
                [3.6, "fill-accent"],
              ].map(([r, cls]) => (
                <circle key={cls} r={r} className={cls as string}>
                  <animateMotion path={replay.path} dur={`${replay.total}s`} begin={`${LEAD}s`} fill="freeze" calcMode="paced" />
                </circle>
              ))}
            </g>
          )}
        </svg>
      </div>

      {/* 凡例とたどり直し */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-caption text-muted">
        <span className="inline-flex items-center gap-1.5">
          <svg width="20" height="6" aria-hidden>
            <line x1="1" y1="3" x2="19" y2="3" strokeWidth="1.6" strokeLinecap="round" className="stroke-accent" />
          </svg>
          {t.chat.flowLegendTaken}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <svg width="20" height="6" aria-hidden>
            <line x1="1" y1="3" x2="19" y2="3" strokeWidth="1" strokeDasharray="3 3" className="stroke-divider-strong" />
          </svg>
          {t.chat.flowLegendNotTaken}
        </span>
        <span className="text-muted-2">{t.chat.flowLegendArc}</span>
        {animate && (
          <Button variant="plain" size="sm" className="ml-auto" onClick={() => setPlay((p) => p + 1)}>
            <Icon name="refresh" size={12} />
            {t.chat.flowReplay}
          </Button>
        )}
      </div>
    </div>
  );
}
