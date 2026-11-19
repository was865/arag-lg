import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { FLOW_GRAPH, answerTimeMs, flowOf, inferNode, nodesOfSteps, routeOf, stepsOfNode, type FlowNodeId, type FlowStep } from "@/lib/chat/flow";

/** api の偽モデルのテストが記録した、分岐ごとのイベントの列（specs/029 T2。節点の名前は除いてある = 古い記録と同じ形） */
const SNAPSHOTS = JSON.parse(
  readFileSync(new URL("../../../../api/tests/fixtures/agent_flow_snapshots.json", import.meta.url), "utf-8"),
) as Record<string, { events: { type: string; step?: Record<string, unknown> }[] }>;

/** イベントの列を、画面と同じく ID ごとに最後の状態へまとめる。 */
function stepsOf(name: string): FlowStep[] {
  const byId = new Map<string, FlowStep>();
  for (const ev of SNAPSHOTS[name].events) {
    if (ev.type !== "step" || !ev.step) continue;
    const s = ev.step as { id: string; name: string; parent_id?: string; status: string; input?: Record<string, unknown>; output?: Record<string, unknown> };
    byId.set(s.id, { id: s.id, name: s.name, parentId: s.parent_id, status: s.status, durationMs: 10, input: s.input ?? {}, output: s.output ?? null });
  }
  return [...byId.values()];
}

const passedIds = (steps: FlowStep[]) => flowOf(steps).nodes.filter((n) => n.passed).map((n) => n.id);
const edge = (steps: FlowStep[], key: string) => flowOf(steps).edges.find((e) => e.key === key)!;
const visits = (steps: FlowStep[], id: FlowNodeId) => flowOf(steps).nodes.find((n) => n.id === id)!.visits;

describe("flowOf（ステップの列 → 通った節点と辺）", () => {
  it("グラフの形は make graph の書き出しに従う", () => {
    expect(FLOW_GRAPH.nodes.map((n) => n.id)).toEqual([
      "read_image", "understand", "primer_search", "investigate", "guard", "review", "finalize", "followups",
    ]);
    expect(FLOW_GRAPH.edges.find((e) => e.key === "send_back")).toMatchObject({ source: "review", target: "investigate", kind: "back" });
  });

  it("そのまま回答: 理解 → 最初の検索 → 調査 → 見張り → 確認 → 確定。画像と続けて聞くは通らない", () => {
    const steps = stepsOf("answer");
    expect(passedIds(steps)).toEqual(["understand", "primer_search", "investigate", "guard", "review", "finalize"]);
    const run = flowOf(steps);
    expect(run).toMatchObject({ sentBack: 0, retried: 0, usedDraft: false, inferred: true });
    expect(edge(steps, "pass").passed).toBe(true);
    expect(edge(steps, "send_back").passed).toBe(false);
  });

  it("調べ残しの差し戻し: 確認 → 調査へ 1 回戻り、調査と確認を 2 回通る", () => {
    const steps = stepsOf("gap");
    const run = flowOf(steps);
    expect(run.sentBack).toBe(1);
    expect(edge(steps, "send_back")).toMatchObject({ passed: true, count: 1, kind: "back" });
    expect(visits(steps, "investigate")).toBe(2);
    expect(visits(steps, "review")).toBe(2);
    // 見直しのステップは確認の節点のもの、書き直しで呼んだ検索は調査の節点のもの
    const { nodes } = nodesOfSteps(steps);
    expect(nodes.get("review-1")).toBe("review");
    expect([...nodes.entries()].filter(([id]) => id.startsWith("<call-")).every(([, n]) => n === "investigate")).toBe(true);
  });

  it("調べ残しの後に数字の差し戻し: 2 回戻る", () => {
    expect(flowOf(stepsOf("gap_then_numbers")).sentBack).toBe(2);
    expect(edge(stepsOf("gap_then_numbers"), "send_back").count).toBe(2);
  });

  it("空の生成のやり直し: 見張り → 調査へ戻る", () => {
    const steps = stepsOf("empty_retry");
    expect(flowOf(steps).retried).toBe(1);
    expect(edge(steps, "retry")).toMatchObject({ passed: true, count: 1 });
    expect(visits(steps, "investigate")).toBe(2);
    // やり直さずに空のまま終わった 2 度目は数えない
    expect(flowOf(stepsOf("empty_retry_then_tools")).retried).toBe(1);
  });

  it("システムの聞き返し: 最初の検索 → 確定へ飛び、調査・見張り・確認は通らない（specs/031）", () => {
    const steps: FlowStep[] = [
      { id: "understand", name: "understand", status: "done", durationMs: 10, input: { history: false }, output: { kind: "docs" } },
      { id: "primer-1", name: "search" as FlowStep["name"], status: "done", durationMs: 10, input: { by: "system", role: "question" }, output: null },
      { id: "system-clarify", name: "system", status: "done", durationMs: 0, input: { kind: "clarify", reason: "document_unspecified" }, output: null },
    ];
    expect(edge(steps, "clarify")).toMatchObject({ passed: true, kind: "skip" });
    expect(edge(steps, "investigate").passed).toBe(false);
    expect(passedIds(steps)).toEqual(["understand", "primer_search", "finalize"]);
  });

  it("下書きへの退避: 見張り → 確定へ飛び、確認からの通過の辺は通らない", () => {
    for (const name of ["empty_after_send_back_uses_draft", "rewrite_reply_uses_draft"]) {
      const steps = stepsOf(name);
      const run = flowOf(steps);
      expect(run.usedDraft).toBe(true);
      expect(edge(steps, "use_draft")).toMatchObject({ passed: true, kind: "skip" });
      expect(edge(steps, "pass").passed).toBe(false);
      expect(visits(steps, "review")).toBe(1);
    }
    expect(flowOf(stepsOf("rewrite_after_tool_kept")).usedDraft).toBe(false);
  });

  it("雑談: 最初の検索を飛ばして調査へ", () => {
    const steps = stepsOf("chat");
    expect(passedIds(steps)).not.toContain("primer_search");
    expect(edge(steps, "chat").passed).toBe(true);
    expect(edge(steps, "docs").passed).toBe(false);
  });

  it("所要時間は節点の親ステップの和。子ステップも節点の一覧に入る", () => {
    const steps = stepsOf("tool_then_answer");
    const run = flowOf(steps);
    const understand = run.nodes.find((n) => n.id === "understand")!;
    // 初回のターンは質問文での検索（primer-1）を理解と並行に行う
    expect(understand.stepIds).toContain("primer-1");
    expect(understand.stepIds.some((id) => id.startsWith("primer-1:"))).toBe(true);
    expect(understand.durationMs).toBe(20);
  });
});

describe("節点の名前（新しい記録）と推定（古い記録）", () => {
  const step = (id: string, name: string, extra: Partial<FlowStep> = {}): FlowStep => ({
    id, name, status: "done", durationMs: 5, input: {}, ...extra,
  });

  it("node があればそれを使い、推定とは示さない", () => {
    const steps = [
      step("understand", "understand", { node: "understand", input: { history: true }, output: { kind: "docs" } }),
      step("primer-1", "search", { node: "primer_search", input: { by: "system" } }),
      step("call_1", "search", { node: "investigate" }),
      step("call_1:r", "retrieve", { parentId: "call_1" }),
      step("system-citation-cleanup", "system", { node: "finalize", input: { kind: "citation_cleanup" } }),
    ];
    const run = flowOf(steps);
    expect(run.inferred).toBe(false);
    expect(stepsOfNode(steps, "investigate").map((s) => s.id)).toEqual(["call_1", "call_1:r"]);
    expect(stepsOfNode(steps, "primer_search").map((s) => s.id)).toEqual(["primer-1"]);
  });

  it("推定の規則: 2 ターン目の primer-1 は最初の検索、見張りと確定の処理は種類で分ける", () => {
    expect(inferNode(step("primer-1", "retrieve", { input: { by: "system" } }), false)).toBe("primer_search");
    expect(inferNode(step("primer-1", "retrieve", { input: { by: "system" } }), true)).toBe("understand");
    expect(inferNode(step("x", "system", { input: { kind: "rewrite_discarded" } }), true)).toBe("guard");
    expect(inferNode(step("x", "system", { input: { kind: "number_check" } }), true)).toBe("finalize");
    expect(inferNode(step("x", "system", { input: { kind: "followups" } }), true)).toBe("followups");
    expect(inferNode(step("x", "system", { input: { kind: "step_budget" } }), true)).toBe("investigate");
    expect(inferNode(step("img-1", "read_image"), true)).toBe("read_image");
    expect(nodesOfSteps(stepsOf("second_turn")).nodes.get("primer-1")).toBe("primer_search");
  });

  it("実行中は、いま動いているステップの節点を示す。確定前なら確定は通っていない", () => {
    const steps = [
      step("understand", "understand", { node: "understand", output: { kind: "docs" } }),
      step("review-1", "review", { node: "review", status: "running" }),
    ];
    const run = flowOf(steps, { running: true });
    expect(run.current).toBe("review");
    expect(run.nodes.find((n) => n.id === "review")!.current).toBe(true);
    expect(run.nodes.find((n) => n.id === "finalize")!.passed).toBe(false);
  });
});

describe("routeOf（実際にたどった順の経路）", () => {
  const path = (name: string) =>
    routeOf(stepsOf(name)).stops.map((s) => `${s.node}${s.round > 1 ? s.round : ""}${s.outcome ? `:${s.outcome}` : ""}`);

  it("そのまま回答: 確認を 1 度通って確定", () => {
    // 見張りも、何もせず通したことを停留所にする（T41）
    expect(path("answer")).toEqual(["understand", "primer_search", "investigate", "guard:passed", "review:passed", "finalize"]);
  });

  it("差し戻し: 2 周目の調査と確認を別の停留所にする（×2 とまとめない）", () => {
    expect(path("gap")).toEqual([
      "understand", "primer_search", "investigate", "guard:passed", "review:sent_back",
      "investigate2", "guard2:passed", "review2:passed", "finalize",
    ]);
    const r = routeOf(stepsOf("gap"));
    expect(r).toMatchObject({ rounds: 2, sentBack: 1, usedDraft: false });
    // 停留所の鍵は周回ごとに違う（一覧を周回ごとに絞れる）
    expect(new Set(r.stops.map((s) => s.key)).size).toBe(r.stops.length);
  });

  it("2 回差し戻すと 3 周目まで並ぶ", () => {
    expect(path("gap_then_numbers").filter((p) => p.startsWith("review"))).toEqual([
      "review:sent_back", "review2:sent_back", "review3:passed",
    ]);
  });

  it("下書きへの退避は見張りの停留所で示し、その周回の確認は並べない", () => {
    const p = path("rewrite_reply_uses_draft");
    expect(p).toContain("guard2:used_draft");
    expect(p.at(-1)).toBe("finalize");
    expect(p.at(-2)).toBe("guard2:used_draft");
  });

  it("雑談は最初の検索を通らず、確認は見直さずに通す", () => {
    const p = path("chat");
    expect(p).not.toContain("primer_search");
    expect(p).toContain("review:skipped");
    expect(routeOf(stepsOf("chat")).chat).toBe(true);
  });

  it("確認の通過の記録が無い古い記録は、通過を推定する", () => {
    const old = stepsOf("answer").filter((s) => s.input?.kind !== "review_passed");
    const review = routeOf(old).stops.find((s) => s.node === "review")!;
    expect(review).toMatchObject({ outcome: "passed", inferred: true, stepIds: [] });
  });

  it("実行中: 差し戻しの直後は、次の周回の調査を今の停留所にする", () => {
    const steps = stepsOf("gap");
    const cut = steps.findIndex((s) => s.name === "review");
    const r = routeOf(steps.slice(0, cut + 1), { running: true });
    const now = r.stops.find((s) => s.current)!;
    expect(now).toMatchObject({ node: "investigate", round: 2 });
  });
});

describe("answerTimeMs（見出しの所要時間）", () => {
  const step = (id: string, ms: number, p: Partial<FlowStep> = {}): FlowStep => ({
    id, name: "search", status: "done", durationMs: ms, input: {}, ...p,
  });
  const fu = step("system-followups", 4000, { name: "system", input: { kind: "followups" }, node: "followups" });

  it("確定した回答は run の所要時間（続けて聞くの時間を含まない）", () => {
    expect(answerTimeMs([step("a", 500), fu], 1200)).toBe(1200);
  });

  it("所要時間が無いあいだは親ステップの和。続けて聞くと子ステップは数えない", () => {
    expect(answerTimeMs([step("a", 500), step("b", 300, { parentId: "a" }), fu], 0)).toBe(500);
    // 節点の名前の無い古い記録でも、種類から続けて聞くと分かる
    expect(answerTimeMs([step("a", 500), { ...fu, node: undefined }])).toBe(500);
  });
});

describe("routeOf の条件つきの辺（specs/029 T32）", () => {
  const via = (steps: FlowStep[]) => routeOf(steps).stops.map((s) => [s.key, s.via?.key ?? null]);

  it("条件つきの辺で着いた停留所に、選ばれた分岐を付ける", () => {
    const v = Object.fromEntries(via(stepsOf("answer")));
    expect(v["primer_search-1"]).toBe("docs");
    expect(v["review-1"]).toBe("ok"); // 見張り → 確認（見張りが通した。T41 から見張りも停留所）
    expect(v["finalize-1"]).toBe("pass");
    expect(Object.fromEntries(via(stepsOf("gap")))["investigate-2"]).toBe("send_back");
    expect(Object.fromEntries(via(stepsOf("chat")))["investigate-1"]).toBe("chat");
  });

  it("続けて聞くを作らなかったときは、通らなかった停留所として「なし」の辺で示す", () => {
    const off: FlowStep = {
      id: "system-followups", name: "system", status: "done", durationMs: 0,
      input: { kind: "followups" }, output: { skipped: "user_setting" }, node: "followups",
    };
    const fu = routeOf([...stepsOf("answer"), off]).stops.at(-1)!;
    expect(fu).toMatchObject({ node: "followups", notRun: true, via: { key: "end", label: "なし" } });
    const ran = routeOf([...stepsOf("answer"), { ...off, output: { questions: ["次は？"] } }]).stops.at(-1)!;
    expect(ran).toMatchObject({ node: "followups", via: { key: "followups", label: "候補あり" } });
    expect(ran.notRun).toBeFalsy();
    // グラフ全体でも、作らなかったなら続けて聞くと確定 → 続けて聞くの辺は通っていない
    const flow = flowOf([...stepsOf("answer"), off]);
    expect(flow.nodes.find((n) => n.id === "followups")!.passed).toBe(false);
    expect(flow.edges.find((e) => e.key === "followups")!.passed).toBe(false);
  });
});

describe("routeOf の時間（specs/029 T35）", () => {
  it("理解と並行に動いた質問文での検索は、最初の検索の時間に入れず parallelMs に分ける", () => {
    const steps: FlowStep[] = [
      { id: "u", name: "understand", status: "done", durationMs: 700, input: { history: false }, output: { kind: "docs" }, node: "understand" },
      { id: "primer-1", name: "retrieve", status: "done", durationMs: 690, input: { by: "system", role: "question" }, output: null, node: "understand" },
      { id: "primer-2", name: "retrieve", status: "done", durationMs: 300, input: { by: "system" }, output: null, node: "primer_search" },
      { id: "m", name: "system", status: "done", durationMs: 1500, input: { kind: "model_call" }, output: null, node: "investigate" },
    ];
    const r = routeOf(steps);
    const primer = r.stops.find((s) => s.node === "primer_search")!;
    expect(primer.durationMs).toBe(300);
    expect(primer.parallelMs).toBe(690);
    expect(r.stops.find((s) => s.node === "investigate")!.durationMs).toBe(1500);
  });
});
