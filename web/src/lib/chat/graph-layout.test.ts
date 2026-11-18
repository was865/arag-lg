import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { FLOW_GRAPH, routeOf, type FlowStep } from "@/lib/chat/flow";
import { G, graphLayout, replayOf, routeEdges } from "@/lib/chat/graph-layout";

const SNAPSHOTS = JSON.parse(
  readFileSync(new URL("../../../../api/tests/fixtures/agent_flow_snapshots.json", import.meta.url), "utf-8"),
) as Record<string, { events: { type: string; step?: Record<string, unknown> }[] }>;

function stepsOf(name: string): FlowStep[] {
  const byId = new Map<string, FlowStep>();
  for (const ev of SNAPSHOTS[name].events) {
    if (ev.type !== "step" || !ev.step) continue;
    const s = ev.step as { id: string; name: string; parent_id?: string; status: string; input?: Record<string, unknown>; output?: Record<string, unknown> };
    byId.set(s.id, { id: s.id, name: s.name, parentId: s.parent_id, status: s.status, durationMs: 10, input: s.input ?? {}, output: s.output ?? null });
  }
  return [...byId.values()];
}

const keys = (name: string) => routeEdges(routeOf(stepsOf(name))).map((e) => `${e.source}>${e.target}`);

describe("graphLayout（弧線図の配置。specs/029 T33）", () => {
  it("節点を定義の順に横に並べ、隣の辺は直線、飛ばす辺と戻る辺は上の弧にする", () => {
    const { nodes, edges } = graphLayout();
    expect(nodes.map((n) => n.id)).toEqual(FLOW_GRAPH.nodes.map((n) => n.id));
    expect(nodes[0]!.x).toBe(G.PAD);
    expect(nodes.at(-1)!.x).toBe(G.W - G.PAD);
    expect(edges).toHaveLength(FLOW_GRAPH.edges.length);
    const by = new Map(edges.map((e) => [e.id, e]));
    expect(by.get("understand-primer_search")!.arc).toBe(false);
    for (const id of ["understand-investigate", "guard-investigate", "review-investigate", "guard-finalize"]) {
      const e = by.get(id)!;
      expect(e.arc, id).toBe(true);
      expect(e.ly, id).toBeLessThan(G.Y); // 線より上
      expect(e.ly, id).toBeGreaterThan(8); // 図からはみ出さない
    }
    // 戻る辺は同じ区間の飛ばす辺より高い
    expect(by.get("review-investigate")!.ly).toBeLessThan(by.get("guard-finalize")!.ly);
  });
});

describe("routeEdges（実際にたどった辺の順）", () => {
  it("そのまま回答: 見張りを通る道で埋める", () => {
    expect(keys("answer")).toEqual([
      "understand>primer_search",
      "primer_search>investigate",
      "investigate>guard",
      "guard>review",
      "review>finalize",
    ]);
  });

  it("差し戻し: 確認から調査へ戻る辺を通る", () => {
    expect(keys("gap")).toContain("review>investigate");
    expect(keys("gap").filter((k) => k === "investigate>guard")).toHaveLength(2);
  });

  it("雑談: 最初の検索を飛ばす辺を通る", () => {
    expect(keys("chat")[0]).toBe("understand>investigate");
  });
});

describe("replayOf（たどり直しの時刻）", () => {
  it("節点に着く時刻は道の順に増え、全体は 1.6〜5 秒に収まる", () => {
    const r = replayOf(routeOf(stepsOf("gap")))!;
    expect(r.total).toBeGreaterThanOrEqual(1.6);
    expect(r.total).toBeLessThanOrEqual(5);
    expect(r.nodeAt.get("understand")).toBe(0);
    const order = ["understand", "primer_search", "investigate", "guard", "review", "finalize"] as const;
    const times = order.map((id) => r.nodeAt.get(id)!);
    expect([...times].sort((a, b) => a - b)).toEqual(times);
    // 戻る辺は初めて通るときに描く
    expect(r.edgeAt.get("review-investigate")!.start).toBeGreaterThan(r.nodeAt.get("review")! - 0.01);
    expect(r.path.startsWith("M ")).toBe(true);
  });

  it("経路が無ければ null", () => {
    expect(replayOf({ stops: [], rounds: 0, sentBack: 0, usedDraft: false, chat: false, inferred: false })).toBeNull();
  });
});
