/**
 * 「グラフ全体」の弧線図の配置と、実行のたどり直し（トークンが節点を順に通る）の時刻（specs/029 T33）。
 * 節点は定義の順に 1 本の横線に並べ、隣どうしの辺は直線、飛ばす辺・戻る辺は上の弧にする。純関数なのでテストできる。
 */
import { FLOW_GRAPH, type FlowGraphEdge, type FlowNodeId, type FlowRoute } from "@/lib/chat/flow";

/** 図の大きさ（viewBox の単位）。Y は節点の並ぶ線の高さ */
export const G = { W: 760, H: 126, Y: 72, PAD: 52, R: 8 } as const;

export interface NodePos {
  id: FlowNodeId;
  x: number;
}

export interface EdgeGeom {
  edge: FlowGraphEdge;
  /** 鍵（source-target）。同じ 2 点を結ぶ辺は無いので一意 */
  id: string;
  /** 描く線（節点の縁から縁まで。矢印の分だけ手前で止める） */
  d: string;
  /** 節点の中心から中心まで（トークンが通る道） */
  centerD: string;
  /** 札を置く位置（弧の頂点か、直線の中点の少し上） */
  lx: number;
  ly: number;
  arc: boolean;
  /** トークンが通る道の長さ（時刻の計算に使う） */
  length: number;
}

const STEP = (G.W - G.PAD * 2) / (FLOW_GRAPH.nodes.length - 1);

/** 3 次ベジエの長さ（16 分割の折れ線で近似） */
function cubicLength(p: [number, number][]): number {
  const at = (t: number): [number, number] => {
    const u = 1 - t;
    const [a, b, c, d] = p as [[number, number], [number, number], [number, number], [number, number]];
    return [
      u * u * u * a[0] + 3 * u * u * t * b[0] + 3 * u * t * t * c[0] + t * t * t * d[0],
      u * u * u * a[1] + 3 * u * u * t * b[1] + 3 * u * t * t * c[1] + t * t * t * d[1],
    ];
  };
  let len = 0;
  let prev = at(0);
  for (let i = 1; i <= 16; i++) {
    const cur = at(i / 16);
    len += Math.hypot(cur[0] - prev[0], cur[1] - prev[1]);
    prev = cur;
  }
  return len;
}

const r1 = (n: number) => Math.round(n * 10) / 10;

/** 節点と辺の位置。 */
export function graphLayout(): { nodes: NodePos[]; edges: EdgeGeom[] } {
  const index = new Map(FLOW_GRAPH.nodes.map((n, i) => [n.id, i]));
  const nodes = FLOW_GRAPH.nodes.map((n, i) => ({ id: n.id, x: r1(G.PAD + i * STEP) }));
  const { Y, R } = G;
  const edges = FLOW_GRAPH.edges.map((e): EdgeGeom => {
    const si = index.get(e.source)!;
    const ti = index.get(e.target)!;
    const xs = nodes[si]!.x;
    const xt = nodes[ti]!.x;
    const id = `${e.source}-${e.target}`;
    if (e.kind === "next" && Math.abs(ti - si) === 1) {
      return {
        edge: e,
        id,
        d: `M ${r1(xs + R + 2)} ${Y} L ${r1(xt - R - 5)} ${Y}`,
        centerD: `L ${xt} ${Y}`,
        lx: r1((xs + xt) / 2),
        ly: Y - 7,
        arc: false,
        length: Math.abs(xt - xs),
      };
    }
    // 飛ばす辺・戻る辺は上の弧。戻る辺は高くして、同じ区間の飛ばす辺と重ならないようにする
    const span = Math.abs(ti - si);
    const depth = 16 + span * 16 + (e.kind === "back" ? 20 : 0);
    const top = Y - depth;
    const y0 = Y - R - 1;
    const y1 = Y - R - 4;
    return {
      edge: e,
      id,
      d: `M ${xs} ${y0} C ${xs} ${top}, ${xt} ${top}, ${xt} ${y1}`,
      centerD: `C ${xs} ${top}, ${xt} ${top}, ${xt} ${Y}`,
      lx: r1((xs + xt) / 2),
      // ベジエの t=0.5 の高さ
      ly: r1(0.125 * y0 + 0.75 * top + 0.125 * y1),
      arc: true,
      length: cubicLength([
        [xs, Y],
        [xs, top],
        [xt, top],
        [xt, Y],
      ]),
    };
  });
  return { nodes, edges };
}

/** グラフの辺をたどって a から b への最短の道（辺の列）。見つからなければ空。 */
function shortestPath(a: FlowNodeId, b: FlowNodeId): FlowGraphEdge[] {
  const prev = new Map<FlowNodeId, FlowGraphEdge>();
  const seen = new Set<FlowNodeId>([a]);
  const queue: FlowNodeId[] = [a];
  while (queue.length) {
    const cur = queue.shift()!;
    if (cur === b) break;
    for (const e of FLOW_GRAPH.edges) {
      if (e.source !== cur || seen.has(e.target)) continue;
      seen.add(e.target);
      prev.set(e.target, e);
      queue.push(e.target);
    }
  }
  if (!seen.has(b)) return [];
  const path: FlowGraphEdge[] = [];
  for (let n = b; n !== a; ) {
    const e = prev.get(n)!;
    path.unshift(e);
    n = e.source;
  }
  return path;
}

/**
 * 実際にたどった辺の順（経路の停留所の間を、グラフの辺でつなぐ）。
 * 経路は何もしなかった見張りを停留所にしないので、調査 → 確認は見張りを通る道で埋める。
 */
export function routeEdges(route: FlowRoute): FlowGraphEdge[] {
  const nodes = route.stops.filter((s) => !s.notRun).map((s) => s.node);
  const out: FlowGraphEdge[] = [];
  for (let i = 1; i < nodes.length; i++) {
    const a = nodes[i - 1]!;
    const b = nodes[i]!;
    if (a === b) continue;
    // 雑談でない回答の理解 → 調査は、最初の検索を通る（停留所が無い古い記録でも雑談の辺にしない）
    if (a === "understand" && b === "investigate" && !route.chat) {
      out.push(...shortestPath(a, "primer_search"), ...shortestPath("primer_search", b));
      continue;
    }
    out.push(...shortestPath(a, b));
  }
  return out;
}

export interface Replay {
  /** トークンが通る道（節点の中心をつなぐ 1 本のパス） */
  path: string;
  /** 全体の時間（秒） */
  total: number;
  /** 各辺を初めて通り始める時刻と、通るのにかかる時間（秒） */
  edgeAt: Map<string, { start: number; dur: number }>;
  /** 各節点に初めて着く時刻（秒） */
  nodeAt: Map<FlowNodeId, number>;
}

/** たどり直しの道と時刻。速さは一定（道の長さに比例した時間）で、全体は 1.6〜5 秒に収める。 */
export function replayOf(route: FlowRoute): Replay | null {
  const seq = routeEdges(route);
  if (!seq.length) return null;
  const { nodes, edges } = graphLayout();
  const geom = new Map(edges.map((g) => [g.id, g]));
  const x = new Map(nodes.map((n) => [n.id, n.x]));
  const len = seq.reduce((a, e) => a + (geom.get(`${e.source}-${e.target}`)?.length ?? 0), 0);
  const total = Math.min(5, Math.max(1.6, len / 420));
  const edgeAt = new Map<string, { start: number; dur: number }>();
  const nodeAt = new Map<FlowNodeId, number>([[seq[0]!.source, 0]]);
  let t = 0;
  let path = `M ${x.get(seq[0]!.source)} ${G.Y}`;
  for (const e of seq) {
    const g = geom.get(`${e.source}-${e.target}`)!;
    const dur = (g.length / len) * total;
    if (!edgeAt.has(g.id)) edgeAt.set(g.id, { start: r2(t), dur: r2(dur) });
    path += ` ${g.centerD}`;
    t += dur;
    if (!nodeAt.has(e.target)) nodeAt.set(e.target, r2(t));
  }
  return { path, total: r2(total), edgeAt, nodeAt };
}

const r2 = (n: number) => Math.round(n * 100) / 100;
