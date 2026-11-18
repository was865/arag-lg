/** 回答の「流れ」の表示用の計算（specs/029 R7〜R9）。
 *
 * 経路は保存しない。ステップの列（各ステップの `node`）から、この回答が通った節点と辺を組み立てる。
 * 節点の並びと辺は `flow-graph.json`（`make graph` がグラフの定義から書き出す。手で直さない）。
 * `node` の無い古い記録は、ステップの種類から節点を推定し、推定したことを `inferred` で示す。
 */
import graph from "@/lib/chat/flow-graph.json";

export type FlowNodeId =
  | "read_image"
  | "understand"
  | "primer_search"
  | "investigate"
  | "guard"
  | "review"
  | "finalize"
  | "followups";

export interface FlowGraphNode {
  id: FlowNodeId;
  label: string;
  description: string;
}

export interface FlowGraphEdge {
  source: FlowNodeId;
  target: FlowNodeId;
  /** next = 隣へ進む、skip = 飛ばして進む、back = 戻る */
  kind: "next" | "skip" | "back";
  /** 条件つきの辺の値（retry・use_draft・send_back など）。無条件の辺には無い */
  key?: string;
  label?: string;
}

export const FLOW_GRAPH = graph as { nodes: FlowGraphNode[]; edges: FlowGraphEdge[] };

/** 流れの計算に要るステップの形（保存済みの ApiStep・画面の ToolCall のどちらでもよい）。 */
export interface FlowStep {
  id: string;
  name: string;
  parentId?: string;
  status: string;
  durationMs: number;
  input: Record<string, unknown>;
  output?: Record<string, unknown> | null;
  node?: string;
  /** 画面の表示名と要約（流れの停留所の短い説明に使う） */
  label?: string;
  summary?: string;
}

export interface FlowNodeRun extends FlowGraphNode {
  /** 通ったか */
  passed: boolean;
  /** 通った回数（差し戻し・やり直しで調査に戻ると増える） */
  visits: number;
  /** この節点が出した親ステップの所要時間の合計（ミリ秒） */
  durationMs: number;
  /** この節点が出したステップの ID（子ステップを含む。一覧を絞るのに使う。R8） */
  stepIds: string[];
  /** 実行中で、いまこの節点にいる */
  current: boolean;
}

export interface FlowEdgeRun extends FlowGraphEdge {
  passed: boolean;
  /** 通った回数（戻りの辺は戻った回数） */
  count: number;
}

export interface FlowRun {
  nodes: FlowNodeRun[];
  edges: FlowEdgeRun[];
  /** 確認で調査へ戻した回数 */
  sentBack: number;
  /** 空の生成をやり直した回数 */
  retried: number;
  /** 差し戻す前の下書きを回答にした（退避） */
  usedDraft: boolean;
  /** 節点の名前の無い古い記録から推定した */
  inferred: boolean;
  /** 実行中ならいまの節点 */
  current?: FlowNodeId;
}

const NODE_IDS = new Set<string>(FLOW_GRAPH.nodes.map((n) => n.id));
const GUARD_KINDS = new Set(["empty_generation", "rewrite_discarded"]);
const FINALIZE_KINDS = new Set(["citation_pruned", "citation_cleanup", "number_check"]);

function kindOf(step: FlowStep): string {
  return step.name === "system" ? String(step.input?.kind ?? "") : "";
}

/**
 * 見出しに出す回答の所要時間。確定した回答は run の所要時間（完了まで。続けて聞く候補の時間を含まない）。
 * 所要時間がまだ無いあいだは親ステップの和で、続けて聞くのステップは数えない（specs/028 R4a）。
 */
export function answerTimeMs(steps: FlowStep[], durationMs?: number): number {
  if (durationMs && durationMs > 0) return durationMs;
  return steps
    .filter((s) => !s.parentId && s.node !== "followups" && kindOf(s) !== "followups")
    .reduce((a, s) => a + (s.durationMs || 0), 0);
}

/** 節点の名前の無いステップの節点を、ステップの種類から推定する（古い記録用）。 */
export function inferNode(step: FlowStep, firstTurn: boolean): FlowNodeId {
  if (step.name === "read_image") return "read_image";
  if (step.name === "understand") return "understand";
  if (step.input?.by === "system") {
    // 初回のターンの質問文での検索（primer-1）は、理解と並行に行う
    return firstTurn && step.id === "primer-1" ? "understand" : "primer_search";
  }
  if (step.name === "review") return "review";
  if (kindOf(step) === "review_passed") return "review";
  const kind = kindOf(step);
  if (GUARD_KINDS.has(kind)) return "guard";
  if (FINALIZE_KINDS.has(kind)) return "finalize";
  if (kind === "followups") return "followups";
  return "investigate";
}

/** 各ステップの節点（子ステップは親の節点）。2 つ目は推定を使ったか。 */
export function nodesOfSteps(steps: FlowStep[]): { nodes: Map<string, FlowNodeId>; inferred: boolean } {
  const understand = steps.find((s) => s.name === "understand");
  const firstTurn = understand?.input?.history === false;
  const byId = new Map(steps.map((s) => [s.id, s]));
  const nodes = new Map<string, FlowNodeId>();
  let inferred = false;
  const resolve = (s: FlowStep, depth = 0): FlowNodeId => {
    const known = nodes.get(s.id);
    if (known) return known;
    let node: FlowNodeId;
    if (s.node && NODE_IDS.has(s.node)) node = s.node as FlowNodeId;
    else if (s.parentId && byId.has(s.parentId) && depth < 8) node = resolve(byId.get(s.parentId)!, depth + 1);
    else {
      node = inferNode(s, firstTurn);
      inferred = true;
    }
    nodes.set(s.id, node);
    return node;
  };
  for (const s of steps) resolve(s);
  return { nodes, inferred };
}

/** 節点で一覧を絞る（R8）。子ステップも含める。 */
export function stepsOfNode<T extends FlowStep>(steps: T[], node: FlowNodeId): T[] {
  const { nodes } = nodesOfSteps(steps);
  return steps.filter((s) => nodes.get(s.id) === node);
}

/** ステップの列から、この回答の流れ（通った節点と辺・回数）を組み立てる。 */
export function flowOf(
  steps: FlowStep[],
  opts: { running?: boolean; /** 実行中で、動いているステップが無いときの節点（既定は最後のステップの節点） */ idle?: FlowNodeId } = {},
): FlowRun {
  const running = Boolean(opts.running);
  const { nodes: nodeOfStep, inferred } = nodesOfSteps(steps);
  const top = steps.filter((s) => !s.parentId);

  const reviewIds = new Set(top.filter((s) => s.name === "review").map((s) => s.id));
  const sentBack = reviewIds.size;
  const empties = top.filter((s) => kindOf(s) === "empty_generation" && s.status !== "running");
  const retried = empties.filter((s) => s.input?.retried === true).length;
  const usedDraft =
    top.some((s) => kindOf(s) === "rewrite_discarded") ||
    empties.some((s) => (s.output as Record<string, unknown> | null | undefined)?.result === "used_draft");
  const understand = [...top].reverse().find((s) => s.name === "understand" && s.status !== "running");
  const kind = (understand?.output as Record<string, unknown> | null | undefined)?.kind;

  const has = (id: FlowNodeId) => top.some((s) => nodeOfStep.get(s.id) === id);
  const finalized = has("finalize") || has("followups") || (!running && steps.length > 0);
  const passed: Record<FlowNodeId, boolean> = {
    read_image: has("read_image"),
    understand: has("understand"),
    // 雑談は最初の検索を飛ばす（理解が終わっていなければまだ分からない）
    primer_search: has("primer_search") || kind === "docs",
    investigate: false,
    guard: false,
    review: false,
    finalize: finalized,
    followups: has("followups"),
  };
  // 調査・見張り・確認は何も出さずに通ることがある。後ろの節点まで進んでいれば通っている
  passed.investigate = has("investigate") || has("guard") || has("review") || finalized;
  passed.guard = has("guard") || has("review") || finalized;
  // 下書きへ退避した回答は、最後の見張りから確認を通らずに確定へ進む（退避は差し戻しの後だけなので確認は通っている）
  passed.review = has("review") || (passed.guard && finalized && !usedDraft);

  const visits: Record<FlowNodeId, number> = {
    read_image: passed.read_image ? 1 : 0,
    understand: passed.understand ? 1 : 0,
    primer_search: passed.primer_search ? 1 : 0,
    investigate: passed.investigate ? 1 + sentBack + retried : 0,
    guard: passed.guard ? 1 + sentBack + retried : 0,
    review: passed.review ? sentBack + (usedDraft ? 0 : 1) : 0,
    finalize: passed.finalize ? 1 : 0,
    followups: passed.followups ? 1 : 0,
  };

  let current: FlowNodeId | undefined;
  if (running) {
    const live = [...top].reverse().find((s) => s.status === "running");
    const last = live ?? top[top.length - 1];
    current = live ? nodeOfStep.get(live.id) : last ? (opts.idle ?? nodeOfStep.get(last.id)) : "understand";
  }

  const nodes: FlowNodeRun[] = FLOW_GRAPH.nodes.map((n) => ({
    ...n,
    passed: passed[n.id],
    visits: visits[n.id],
    durationMs: top.filter((s) => nodeOfStep.get(s.id) === n.id).reduce((a, s) => a + (s.durationMs || 0), 0),
    stepIds: steps.filter((s) => nodeOfStep.get(s.id) === n.id).map((s) => s.id),
    current: current === n.id,
  }));

  const count = (e: FlowGraphEdge): number => {
    const both = passed[e.source] && passed[e.target];
    switch (e.key) {
      case "retry":
        return retried;
      case "send_back":
        return sentBack;
      case "use_draft":
        return usedDraft ? 1 : 0;
      case "ok":
        return passed.review ? visits.review : 0;
      case "pass":
        return passed.review && passed.finalize && !usedDraft ? 1 : 0;
      case "chat":
        return kind === "chat" ? 1 : 0;
      case "docs":
        return passed.primer_search ? 1 : 0;
      default:
        if (e.source === "investigate" && e.target === "guard") return passed.guard ? visits.guard : 0;
        return both ? 1 : 0;
    }
  };
  const edges: FlowEdgeRun[] = FLOW_GRAPH.edges.map((e) => {
    const n = count(e);
    return { ...e, count: n, passed: n > 0 };
  });

  return { nodes, edges, sentBack, retried, usedDraft, inferred, current };
}

// ── 実際にたどった順の経路（「詳細」の流れの表示。specs/029 R7） ──

/** 経路の 1 つの停留所の結果。確認・見張りだけが持つ。 */
export type StopOutcome = "sent_back" | "passed" | "skipped" | "retried" | "used_draft" | "failed";

export interface FlowStop {
  /** 一覧を絞るときの鍵（`investigate-2` など。同じ節点を何度も通るので節点名とは別） */
  key: string;
  node: FlowNodeId;
  label: string;
  /** 調査・見張り・確認の周回（1 始まり） */
  round: number;
  outcome?: StopOutcome;
  /** この停留所の親ステップ（時刻順） */
  steps: FlowStep[];
  /** 子ステップを含むステップの ID（一覧を絞るのに使う） */
  stepIds: string[];
  durationMs: number;
  current: boolean;
  /** 記録が無く、後ろの停留所から推定した（古い記録の確認の通過など） */
  inferred?: boolean;
}

export interface FlowRoute {
  stops: FlowStop[];
  /** 調査の周回の数 */
  rounds: number;
  sentBack: number;
  usedDraft: boolean;
  chat: boolean;
  inferred: boolean;
}

const LABEL = new Map(FLOW_GRAPH.nodes.map((n) => [n.id, n.label]));

function guardOutcome(s: FlowStep): StopOutcome | undefined {
  const kind = kindOf(s);
  if (kind === "rewrite_discarded") return "used_draft";
  if (kind !== "empty_generation") return undefined;
  const result = (s.output as Record<string, unknown> | null | undefined)?.result;
  return result === "used_draft" ? "used_draft" : result === "failed" ? "failed" : "retried";
}

/**
 * ステップの列から、この回答が実際にたどった順の経路を作る。
 * 調査 → 確認で差し戻されたら、次の調査は「2 周目」として新しい停留所にする（同じ節点を ×2 とまとめない）。
 * 見張りは何かをしたとき（やり直し・下書きへの退避）だけ停留所にする。
 */
export function routeOf(steps: FlowStep[], opts: { running?: boolean } = {}): FlowRoute {
  const running = Boolean(opts.running);
  const { nodes: nodeOf, inferred } = nodesOfSteps(steps);
  const top = steps.filter((s) => !s.parentId);
  const children = new Map<string, string[]>();
  for (const s of steps) {
    if (!s.parentId) continue;
    // 子の子も、いちばん上の親に寄せる
    let root = s;
    for (let i = 0; i < 8 && root.parentId; i++) root = steps.find((x) => x.id === root.parentId) ?? { ...root, parentId: undefined };
    children.set(root.id, [...(children.get(root.id) ?? []), s.id]);
  }
  const stop = (node: FlowNodeId, round: number, own: FlowStep[], extra: Partial<FlowStop> = {}): FlowStop => ({
    key: `${node}-${round}`,
    node,
    label: LABEL.get(node) ?? node,
    round,
    steps: own,
    stepIds: own.flatMap((s) => [s.id, ...(children.get(s.id) ?? [])]),
    durationMs: own.reduce((a, s) => a + (s.durationMs || 0), 0),
    current: false,
    ...extra,
  });
  const of = (id: FlowNodeId) => top.filter((s) => nodeOf.get(s.id) === id);

  const stops: FlowStop[] = [];
  // 初回のターンは質問文での検索を理解と並行に行う（節点は理解）。見せるときは自動の検索をまとめて「最初の検索」に
  const auto = (s: FlowStep) => s.input?.by === "system";
  const prelude: [FlowNodeId, FlowStep[]][] = [
    ["read_image", of("read_image")],
    ["understand", of("understand").filter((s) => !auto(s))],
    ["primer_search", [...of("understand").filter(auto), ...of("primer_search")]],
  ];
  for (const [id, own] of prelude) if (own.length) stops.push(stop(id, 1, own));
  const understand = [...top].reverse().find((s) => s.name === "understand" && s.status !== "running");
  const chat = (understand?.output as Record<string, unknown> | null | undefined)?.kind === "chat";

  // 調査・見張り・確認を周回に分ける（確認か見張りの退避の後に来た調査は次の周回）
  type Round = { inv: FlowStep[]; guard: FlowStep[]; review?: FlowStep };
  const rounds: Round[] = [];
  let cur: Round | undefined;
  const fresh = () => {
    cur = { inv: [], guard: [] };
    rounds.push(cur);
    return cur;
  };
  for (const s of top) {
    const node = nodeOf.get(s.id);
    if (node !== "investigate" && node !== "guard" && node !== "review") continue;
    const r = !cur || cur.review ? fresh() : cur;
    if (node === "investigate") r.inv.push(s);
    else if (node === "guard") r.guard.push(s);
    else r.review = s;
  }
  const finals = of("finalize");
  const followups = of("followups");
  const finalized = finals.length > 0 || followups.length > 0 || (!running && steps.length > 0);
  // 差し戻しの後で、まだ何も記録の無い書き直しの周回（実行中）
  const last = rounds[rounds.length - 1];
  if (running && !finalized && (!last || last.review?.name === "review")) fresh();
  // 古い記録・何もツールを使わない回答でも、確定まで進んだなら調査は通っている
  if (!rounds.length && finalized) fresh();

  let sentBack = 0;
  let usedDraft = false;
  rounds.forEach((r, i) => {
    const n = i + 1;
    stops.push(stop("investigate", n, r.inv));
    for (const g of r.guard) {
      const outcome = guardOutcome(g);
      if (!outcome) continue;
      if (outcome === "used_draft") usedDraft = true;
      stops.push({ ...stop("guard", n, [g], { outcome }), key: `guard-${n}-${g.id}` });
    }
    if (r.review) {
      if (r.review.name === "review") sentBack += 1;
      const outcome: StopOutcome =
        r.review.name === "review" ? "sent_back" : r.review.input?.skip ? "skipped" : "passed";
      stops.push(stop("review", n, [r.review], { outcome }));
    } else if (i === rounds.length - 1 && finalized && !usedDraft) {
      // 確認の通過を記録していない古い記録。確定まで進んだので、確認は通っている
      stops.push(stop("review", n, [], { outcome: chat ? "skipped" : "passed", inferred: true }));
    }
  });
  if (finalized) stops.push(stop("finalize", 1, finals));
  if (followups.length) stops.push(stop("followups", 1, followups));

  if (running && stops.length) {
    const live = stops.findLast((s) => s.steps.some((x) => x.status === "running"));
    if (live) live.current = true;
    else {
      // 動いているステップが無いあいだは、モデルが考えるか書いている（最後の調査）。確定まで進んでいれば最後
      const end = stops[stops.length - 1]!;
      const passedReview = end.node === "review" && end.outcome !== "sent_back";
      const target = finalized || passedReview ? end : stops.findLast((s) => s.node === "investigate");
      if (target) target.current = true;
      else stops.push({ ...stop("investigate", 1, []), current: true });
    }
  }
  return { stops, rounds: rounds.length, sentBack, usedDraft, chat, inferred };
}
