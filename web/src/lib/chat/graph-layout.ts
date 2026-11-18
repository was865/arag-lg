/**
 * グラフの実行経路の図の配置（specs/029 T34）。節点を定義の順に 1 本の線に並べ、隣どうしの辺は直線、
 * 飛ばす辺・戻る辺は弧にする。横（広い画面）は弧を上に、縦（狭い画面）は弧を左に描く。純関数なのでテストできる。
 *
 * 計算は線に沿った位置 u と、線から離れる量 v で行い、向きに合わせて x・y に直す。
 */
import { FLOW_GRAPH, type FlowGraphEdge, type FlowNodeId } from "@/lib/chat/flow";

export type Orient = "row" | "column";

/** 図の大きさ（viewBox の単位）。row は幅に合わせて伸縮し、column は等倍で描く */
export const LAYOUT = {
  row: { W: 760, H: 96, PAD: 44, LINE: 56 },
  column: { W: 360, PAD: 18, STEP: 30, LINE: 84 },
  /** 節点の半径 */
  R: 5,
} as const;

export interface NodePos {
  id: FlowNodeId;
  x: number;
  y: number;
}

export interface EdgeGeom {
  edge: FlowGraphEdge;
  /** source-target（同じ 2 点を結ぶ辺は無いので一意） */
  id: string;
  d: string;
  /** 札を置く位置（弧の頂点。直線の辺は中点） */
  lx: number;
  ly: number;
  arc: boolean;
}

export interface GraphLayout {
  orient: Orient;
  width: number;
  height: number;
  nodes: NodePos[];
  edges: EdgeGeom[];
}

const r1 = (n: number) => Math.round(n * 10) / 10;

/** 節点と辺の位置。 */
export function graphLayout(orient: Orient): GraphLayout {
  const n = FLOW_GRAPH.nodes.length;
  const R = LAYOUT.R;
  const row = orient === "row";
  const step = row ? (LAYOUT.row.W - LAYOUT.row.PAD * 2) / (n - 1) : LAYOUT.column.STEP;
  const pad = row ? LAYOUT.row.PAD : LAYOUT.column.PAD;
  const line = row ? LAYOUT.row.LINE : LAYOUT.column.LINE;
  // (u: 線に沿った位置, v: 線から離れる量) → (x, y)。横は上へ、縦は左へ離れる
  const pt = (u: number, v: number): [number, number] => (row ? [r1(u), r1(line - v)] : [r1(line - v), r1(u)]);
  const P = (u: number, v: number) => pt(u, v).join(" ");

  const index = new Map(FLOW_GRAPH.nodes.map((x, i) => [x.id, i]));
  const uOf = (i: number) => pad + i * step;
  const nodes = FLOW_GRAPH.nodes.map((x, i) => {
    const [px, py] = pt(uOf(i), 0);
    return { id: x.id, x: px, y: py };
  });
  const edges = FLOW_GRAPH.edges.map((e): EdgeGeom => {
    const si = index.get(e.source)!;
    const ti = index.get(e.target)!;
    const us = uOf(si);
    const ut = uOf(ti);
    const id = `${e.source}-${e.target}`;
    if (e.kind === "next" && Math.abs(ti - si) === 1) {
      const [lx, ly] = pt((us + ut) / 2, 0);
      return { edge: e, id, d: `M ${P(us + R + 2, 0)} L ${P(ut - R - 4, 0)}`, lx, ly, arc: false };
    }
    // 飛ばす辺・戻る辺。戻る辺は離して、同じ区間の飛ばす辺と重ならないようにする
    const span = Math.abs(ti - si);
    const depth = 12 + span * 11 + (e.kind === "back" ? 12 : 0);
    const v0 = R + 1;
    const v1 = R + 4;
    const [lx, ly] = pt((us + ut) / 2, 0.125 * v0 + 0.75 * depth + 0.125 * v1);
    return {
      edge: e,
      id,
      d: `M ${P(us, v0)} C ${P(us, depth)}, ${P(ut, depth)}, ${P(ut, v1)}`,
      lx,
      ly,
      arc: true,
    };
  });
  const width = row ? LAYOUT.row.W : LAYOUT.column.W;
  const height = row ? LAYOUT.row.H : r1(pad * 2 + (n - 1) * step);
  return { orient, width, height, nodes, edges };
}
