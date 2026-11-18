import { describe, expect, it } from "vitest";
import { FLOW_GRAPH } from "@/lib/chat/flow";
import { LAYOUT, graphLayout } from "@/lib/chat/graph-layout";

describe("graphLayout（実行経路の図の配置。specs/029 T34）", () => {
  it("横: 節点を定義の順に左から並べ、飛ばす辺・戻る辺は線より上の弧にする", () => {
    const g = graphLayout("row");
    expect(g.nodes.map((n) => n.id)).toEqual(FLOW_GRAPH.nodes.map((n) => n.id));
    expect(g.nodes[0]!.x).toBe(LAYOUT.row.PAD);
    expect(g.nodes.at(-1)!.x).toBe(LAYOUT.row.W - LAYOUT.row.PAD);
    expect(new Set(g.nodes.map((n) => n.y)).size).toBe(1);
    expect(g.edges).toHaveLength(FLOW_GRAPH.edges.length);
    const by = new Map(g.edges.map((e) => [e.id, e]));
    expect(by.get("understand-primer_search")!.arc).toBe(false);
    for (const id of ["understand-investigate", "guard-investigate", "review-investigate", "guard-finalize"]) {
      const e = by.get(id)!;
      expect(e.arc, id).toBe(true);
      expect(e.ly, id).toBeLessThan(LAYOUT.row.LINE);
      expect(e.ly, id).toBeGreaterThan(8);
    }
    // 戻る辺は同じ区間の飛ばす辺より離れる
    expect(by.get("review-investigate")!.ly).toBeLessThan(by.get("guard-finalize")!.ly);
  });

  it("縦: 節点を上から並べ、弧は線より左に描く（図からはみ出さない）", () => {
    const g = graphLayout("column");
    expect(new Set(g.nodes.map((n) => n.x)).size).toBe(1);
    expect(g.nodes.map((n) => n.y)).toEqual([...g.nodes.map((n) => n.y)].sort((a, b) => a - b));
    expect(g.height).toBeGreaterThan(g.nodes.at(-1)!.y);
    for (const e of g.edges.filter((x) => x.arc)) {
      expect(e.lx, e.id).toBeLessThan(LAYOUT.column.LINE);
      expect(e.lx, e.id).toBeGreaterThan(30); // 札（中央寄せで幅 60 ほど）が左に切れない
    }
  });
});
