"use client";

import { Fragment, useState } from "react";
import { Segmented } from "@/components/ui/segmented";
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

/** 段階の説明（make graph が書き出す節点の説明。停留所の名前のホバーで読む）。 */
const DESCRIPTION = new Map(FLOW_GRAPH.nodes.map((n) => [n.id, n.description]));

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
  if (s.notRun)
    return <span className={cn(base, "border-[1.5px] border-dashed border-divider-strong bg-surface")} />;
  switch (s.outcome) {
    case "sent_back": // 戻る矢印
      return <span className={cn(base, "bg-accent-soft text-accent")}>{glyph("M6 4L3 7l3 3M3.5 7H10a3 3 0 010 6H8")}</span>;
    case "passed":
      return (
        <span className={cn(base, "bg-accent-fill text-white", s.inferred && "bg-accent-soft text-accent")}>
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

/** 札を書く分岐（いつもと違う経路）。資料・通過・候補ありはいつもの経路なので書かない（停留所の印で分かる） */
const UNUSUAL_EDGES = new Set(["chat", "send_back", "retry", "use_draft", "end"]);

/** 経路に並べるもの: 停留所と、回答を利用者に送った時点（確定の節点が run.completed を送る。T32） */
type RouteItem = { kind: "stop"; s: FlowStop } | { kind: "sent" };

/**
 * グラフの実行経路。この回答が実際にたどった順に節点を並べる。差し戻されたら「2 周目」の調査・確認を続けて並べる
 * （同じ節点を ×2 にまとめない）。条件つきの辺には選ばれた分岐を書き、確定の後に「回答を送信」を置く。
 * 幅があり停留所が少なければ横一列、狭いか長い経路は縦に並べる。停留所を押すと、そこで出たステップだけに一覧を絞る（R8）。
 * flow を渡すと、「グラフ全体」（通らなかった節点と辺を含む）に切り替えられる。
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
  /** グラフ全体の表示に使う（通った節点・辺と回数） */
  flow?: FlowRun;
  running?: boolean;
  /** run の所要時間（回答を送るまで）。「回答を送信」に添える */
  durationMs?: number;
  selected?: string | null;
  onSelect?: (key: string | null) => void;
}) {
  const { t } = useT();
  const [view, setView] = useState<"route" | "graph">("route");
  const { stops } = route;
  const items: RouteItem[] = [];
  for (const s of stops) {
    items.push({ kind: "stop", s });
    if (s.node === "finalize" && !running && durationMs > 0) items.push({ kind: "sent" });
  }
  // 横一列は 8 つまで（それより長い経路は縦の方が読みやすい）
  const wide = items.length <= 8;
  const row = (cls: string) => (wide ? cls : "");
  const picked = stops.find((s) => s.key === selected);
  const summary = summaryOf(route, running, t);
  const name = (s: FlowStop) => (s.round > 1 ? `${s.label}（${interpolate(t.chat.flowRound, { n: String(s.round) })}）` : s.label);
  const graph = view === "graph" && flow;

  return (
    <div className="@container border-b-[0.5px] border-divider px-3.5 pb-3 pt-2.5 max-md:px-3">
      <div className="mb-2.5 flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-caption font-semibold text-muted">{t.chat.flowTitle}</span>
        {summary && !graph && <span className="text-caption text-fg-2">{summary}</span>}
        <span className="ml-auto flex items-center gap-2">
          {route.inferred && <span className="text-caption text-muted-2">{t.chat.flowInferred}</span>}
          {flow && (
            <Segmented
              label={t.chat.flowTitle}
              value={view}
              options={[
                ["route", t.chat.flowViewRoute],
                ["graph", t.chat.flowViewGraph],
              ]}
              onChange={setView}
            />
          )}
        </span>
      </div>
      {graph ? (
        <GraphView flow={flow} />
      ) : (
        <ol className={cn("m-0 flex list-none flex-col p-0", row("@[480px]:flex-row @[480px]:pt-2"))}>
          {items.map((it, i) => {
            const next = items[i + 1];
            const via = next?.kind === "stop" && next.s.via && UNUSUAL_EDGES.has(next.s.via.key) ? next.s.via : undefined;
            const s = it.kind === "stop" ? it.s : undefined;
            // 次への線。差し戻し・やり直しの後は戻ってやり直す区間、送信の後と通らなかった節点へは点線にする
            const line = next && (
              <span
                aria-hidden
                style={{ animationDelay: `${i * 45 + 120}ms` }}
                className={cn(
                  "absolute left-[7.5px] top-[19px] bottom-[3px] w-0 animate-draw border-l motion-reduce:animate-none",
                  row("@[480px]:bottom-auto @[480px]:left-[calc(50%+11px)] @[480px]:right-[calc(-50%+11px)] @[480px]:top-[7.5px] @[480px]:h-0 @[480px]:w-auto @[480px]:border-l-0 @[480px]:border-t"),
                  s?.outcome === "sent_back" || s?.outcome === "retried"
                    ? "border-dashed border-accent/60"
                    : it.kind === "sent" || (next.kind === "stop" && next.s.notRun)
                      ? "border-dashed border-divider-strong"
                      : "border-accent/35",
                )}
              />
            );
            // 条件つきの辺で選ばれた分岐（縦では線の横、横一列では線の上）
            const edge = via && (
              <span
                data-edge={via.key}
                className={cn(
                  "absolute bottom-0.5 left-[22px] z-[1] whitespace-nowrap font-mono text-[10px] leading-none",
                  row("@[480px]:bottom-auto @[480px]:left-full @[480px]:top-[-7px] @[480px]:-translate-x-1/2"),
                  via.key === "send_back" || via.key === "retry" || via.key === "use_draft" ? "text-accent" : "text-muted-2",
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
            if (it.kind === "sent") {
              return (
                <li key="sent" style={{ animationDelay: `${i * 45}ms` }} className={liCls} title={t.chat.flowSentHint}>
                  {line}
                  {edge}
                  <div
                    className={cn(
                      "flex w-full min-w-0 items-start gap-2.5",
                      row("@[480px]:flex-col @[480px]:items-center @[480px]:gap-1.5 @[480px]:px-1 @[480px]:text-center"),
                    )}
                  >
                    <SentMark />
                    <span className={cn("flex min-w-0 flex-1 items-baseline gap-2", row("@[480px]:w-full @[480px]:flex-col @[480px]:items-center @[480px]:gap-0"))}>
                      <span className={cn("shrink-0 text-footnote font-medium text-fg", row("@[480px]:text-caption"))}>{t.chat.flowSent}</span>
                      <span className={cn("nums shrink-0 font-mono text-[10px] text-muted-2", row("@[480px]:mt-0.5"))}>{formatMs(durationMs)}</span>
                    </span>
                  </div>
                </li>
              );
            }
            const st = it.s;
            const detail = detailOf(st, t);
            const active = selected === st.key;
            const usable = Boolean(onSelect) && st.stepIds.length > 0;
            return (
              <li key={st.key} style={{ animationDelay: `${i * 45}ms` }} className={liCls}>
                {line}
                {edge}
                <button
                  type="button"
                  disabled={!usable}
                  aria-pressed={active}
                  title={usable ? undefined : t.chat.flowNoSteps}
                  onClick={() => onSelect?.(active ? null : st.key)}
                  className={cn(
                    "group flex w-full min-w-0 items-start gap-2.5 rounded-control border-0 bg-transparent p-0 text-left outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
                    row("@[480px]:flex-col @[480px]:items-center @[480px]:gap-1.5 @[480px]:px-1 @[480px]:text-center"),
                    usable ? "cursor-pointer" : "cursor-default",
                    st.notRun && "opacity-60",
                  )}
                >
                  <span className={cn("rounded-full transition-shadow duration-(--duration-mid)", active && "ring-[3px] ring-accent/25")}>
                    <StopMark s={st} />
                  </span>
                  <span className={cn("flex min-w-0 flex-1 items-baseline gap-2", row("@[480px]:w-full @[480px]:flex-col @[480px]:items-center @[480px]:gap-0"))}>
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
                    </span>
                    <span
                      className={cn(
                        "min-w-0 flex-1 truncate text-caption",
                        st.outcome === "sent_back" || st.outcome === "used_draft" ? "text-accent" : "text-muted",
                        st.outcome === "failed" && "text-danger",
                        // 横一列では 2 行まで折り返す（理由が切れて読めないのを防ぐ）
                        row("@[480px]:line-clamp-2 @[480px]:w-full @[480px]:flex-none @[480px]:whitespace-pre-line @[480px]:leading-snug"),
                      )}
                      title={detail.replace("\n", " ")}
                    >
                      {detail}
                    </span>
                    {st.durationMs > 0 && (
                      <span className={cn("nums shrink-0 font-mono text-[10px] text-muted-2", row("@[480px]:mt-0.5"))}>
                        {formatMs(st.durationMs)}
                      </span>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      )}
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

/** 回答を送った時点の印（送信のボタンと同じ上向きの矢印。朱は送信に使う色） */
function SentMark() {
  return (
    <span className="relative z-[1] grid h-4 w-4 shrink-0 place-items-center rounded-full bg-accent-fill text-white">
      <svg viewBox="0 0 16 16" width="10" height="10" aria-hidden>
        <path d="M8 12.5V4M4.5 7.5L8 4l3.5 3.5" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

/**
 * グラフ全体（T32）。make graph が書き出した節点をすべて定義の順に並べ、通った回数と時間を添える。
 * 通らなかった節点は淡く出す。条件つきの辺は、選ばれた回数か「通らず」を一覧にする。
 */
export function GraphView({ flow }: { flow: FlowRun }) {
  const { t } = useT();
  const label = new Map(flow.nodes.map((n) => [n.id, n.label]));
  const conditional = flow.edges.filter((e) => e.key);
  return (
    <div className="flex flex-col gap-3">
      <ol className="m-0 grid list-none grid-cols-4 gap-x-1 gap-y-2.5 p-0 @[480px]:grid-cols-8">
        {flow.nodes.map((n) => (
          <li
            key={n.id}
            title={n.description}
            className={cn("flex min-w-0 flex-col items-center gap-1 text-center", !n.passed && "opacity-50")}
          >
            {n.passed ? (
              <span className="grid h-4 w-4 place-items-center rounded-full border-[1.5px] border-accent/55 bg-surface">
                <span className="h-1.5 w-1.5 rounded-full bg-accent/80" />
              </span>
            ) : (
              <span className="h-4 w-4 rounded-full border-[1.5px] border-dashed border-divider-strong bg-surface" />
            )}
            <span className="max-w-full truncate text-caption font-medium text-fg">
              {n.label}
              {n.visits > 1 && <span className="nums ml-0.5 font-mono text-[10px] text-accent">×{n.visits}</span>}
            </span>
            <span className="nums font-mono text-[10px] text-muted-2">
              {n.passed ? (n.durationMs > 0 ? formatMs(n.durationMs) : "") : t.chat.flowNotPassed}
            </span>
          </li>
        ))}
      </ol>
      <div>
        <div className="eyebrow mb-1 text-muted">{t.chat.flowConditionalEdges}</div>
        <ul className="m-0 grid list-none grid-cols-1 gap-x-4 p-0 @[480px]:grid-cols-2">
          {conditional.map((e) => (
            <li
              key={`${e.source}-${e.key}`}
              className={cn("flex min-w-0 items-baseline gap-2 py-0.5 text-caption", !e.passed && "opacity-50")}
            >
              <span className="truncate text-fg-2">
                {label.get(e.source)} → {label.get(e.target)}
              </span>
              <span className={cn("shrink-0 font-mono text-[10px]", e.kind === "back" ? "text-accent" : "text-muted")}>{e.label}</span>
              <span className="nums ml-auto shrink-0 font-mono text-[10px] text-muted-2">
                {e.passed ? interpolate(t.chat.flowEdgeCount, { n: String(e.count) }) : t.chat.flowNotPassed}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
