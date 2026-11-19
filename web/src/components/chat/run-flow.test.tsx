import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { FlowRail, RunFlow } from "@/components/chat/run-flow";
import type { ToolCall } from "@/lib/types";
import { flowOf, routeOf, type FlowStep } from "@/lib/chat/flow";
import { LocaleProvider } from "@/i18n/context";
import { ja } from "@/i18n/locales/ja";

const SNAPSHOTS = JSON.parse(
  readFileSync(new URL("../../../../api/tests/fixtures/agent_flow_snapshots.json", import.meta.url), "utf-8"),
) as Record<string, { events: { type: string; step?: Record<string, unknown> }[] }>;

function stepsOf(name: string): FlowStep[] {
  const byId = new Map<string, FlowStep>();
  for (const ev of SNAPSHOTS[name].events) {
    if (ev.type !== "step" || !ev.step) continue;
    const s = ev.step as { id: string; name: string; label?: string; summary?: string; parent_id?: string; status: string; input?: Record<string, unknown>; output?: Record<string, unknown> };
    byId.set(s.id, { id: s.id, name: s.name, label: s.label, summary: s.summary, parentId: s.parent_id, status: s.status, durationMs: 10, input: s.input ?? {}, output: s.output ?? null });
  }
  return [...byId.values()];
}

const wrap = (el: React.ReactNode) =>
  renderToStaticMarkup(
    <LocaleProvider locale="ja" dict={ja}>
      {el}
    </LocaleProvider>,
  );

describe("RunFlow（グラフの実行経路。specs/029 R7・T35）", () => {
  const text = (html: string) => html.replace(/<title>[^<]*<\/title>/g, " ").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
  const view = (name: string, p: Partial<React.ComponentProps<typeof RunFlow>> = {}) =>
    wrap(<RunFlow route={routeOf(stepsOf(name))} flow={flowOf(stepsOf(name))} {...p} />);
  const graph = (name: string, p: Partial<React.ComponentProps<typeof RunFlow>> = {}) => view(name, { defaultView: "graph", ...p });

  it("見出しは「グラフの実行経路」。ひと言の要約はいつもと違う経路だけ。経路とグラフを切り替えられる", () => {
    expect(text(view("answer"))).toContain("グラフの実行経路");
    expect(text(view("answer"))).toMatch(/経路.*グラフ/);
    expect(text(view("answer"))).not.toContain("確認をそのまま通過");
    expect(text(view("gap"))).toContain("確認で 1 回差し戻し、書き直して通過");
    expect(text(view("gap", { running: true }))).not.toContain("書き直して通過");
  });

  describe("経路（既定）: 実際にたどった順", () => {
    it("差し戻しの後は 2 周目として続けて並べ、差し戻しの分岐に札を書く", () => {
      const html = view("gap");
      expect(html).not.toContain("data-orient");
      const order = [...html.matchAll(/data-stop="([^"]+)"/g)].map((m) => m[1]);
      expect(order).toEqual([
        "understand-1", "primer_search-1", "investigate-1", "guard-1-system-guard-pass-1", "review-1",
        "investigate-2", "guard-2-system-guard-pass-2", "review-2", "finalize-1",
      ]);
      expect(text(html)).toContain("調査（2 周目）");
      expect(html).toMatch(/data-edge="send_back"[^>]*>差し戻し</);
      // いつもの分岐（資料・通過）は札を書かない
      expect(html).not.toMatch(/data-edge="docs"/);
    });

    it("段階ごとに時間を出し、モデルの応答の時間も調査に入る（足すと回答までの時間に近づく）", () => {
      const steps = stepsOf("answer");
      const route = routeOf(steps);
      const inv = route.stops.find((s) => s.node === "investigate")!;
      expect(inv.steps.some((s) => s.input?.kind === "model_call")).toBe(true);
      expect(inv.durationMs).toBeGreaterThan(0);
      // 調査の説明はツールの名前（モデルの応答・システムの処理は数えない）
      expect(text(view("answer"))).not.toMatch(/モデルの応答/);
    });

    it("確定の後に「回答を送信」と所要時間を置く（実行中は置かない）", () => {
      expect(text(view("answer", { durationMs: 3120 }))).toContain("回答を送信 3.12s");
      expect(view("answer", { durationMs: 3120, running: true })).not.toContain("data-sent");
    });

    it("段階を押すと、その周回で絞る", () => {
      const html = view("gap", { selected: "review-1", onSelect: () => {} });
      expect(html).toMatch(/data-stop="review-1"[\s\S]*?aria-pressed="true"/);
      expect(text(html)).toContain("確認のステップだけを表示中");
    });

    it("続けて聞くを作らなかったときは「なし」の辺で淡い停留所につなぐ", () => {
      const off: FlowStep = {
        id: "system-followups", name: "system", status: "done", durationMs: 0,
        input: { kind: "followups" }, output: { skipped: "user_setting" }, node: "followups",
      };
      const steps = [...stepsOf("answer"), off];
      const html = wrap(<RunFlow route={routeOf(steps)} flow={flowOf(steps)} durationMs={1000} />);
      expect(text(html)).toContain("設定でオフ");
      expect(html).toMatch(/data-edge="end"[^>]*>なし</);
    });
  });

  describe("グラフ: 節点と辺の全体", () => {
    it("同じ図を横と縦の 2 つの向きで持ち、すべての節点を並べる", () => {
      const html = graph("answer");
      expect(html).toContain('data-orient="row"');
      expect(html).toContain('data-orient="column"');
      for (const id of ["read_image", "understand", "primer_search", "investigate", "guard", "review", "finalize", "followups"])
        expect(html).toContain(`data-node="${id}"`);
    });

    it("通った辺と通らなかった辺を分け、札はいつもと違う分岐だけ。周回は ×n とホバーの内訳", () => {
      const html = graph("gap");
      expect(html).toMatch(/data-edge="send_back" data-taken="1"/);
      expect(html).toMatch(/data-edge="chat" data-taken="0"/);
      expect(text(html)).toContain("差し戻し ×1");
      expect(text(html)).toContain("×2");
      expect(html).toMatch(/<title>確認 — [^<]*1 周目: 差し戻し/);
    });

    it("経路で選んだ周回は、グラフでもその節点を選んだものとして見せる", () => {
      const html = graph("gap", { selected: "review-2", onSelect: () => {} });
      expect(html).toMatch(/data-node="review" role="button" tabindex="0" aria-pressed="true"/);
      expect(html).not.toMatch(/data-node="read_image" role="button"/);
    });

    it("朱は送信の点だけ（横と縦の 2 つ）", () => {
      expect(graph("answer", { durationMs: 3120 }).match(/fill-accent/g)).toHaveLength(2);
    });
  });

  it("節点の名前の無い古い記録は、推定を含むことを示す", () => {
    expect(view("answer")).toContain("古い記録のため一部は推定です");
  });
});

describe("FlowRail（実行中の段階の列）", () => {
  it("動いているステップが無いあいだは idle の節点を今の段階にする", () => {
    const steps = stepsOf("answer").slice(0, 2).map((s) => ({ ...s, status: "done" }));
    const flow = flowOf(steps, { running: true, idle: "investigate" });
    expect(flow.current).toBe("investigate");
    const html = wrap(<FlowRail flow={flow} />);
    expect(html).toMatch(/text-accent[^"]*"><span class="h-1.5[^>]*><\/span>調査/);
  });
});

describe("経路とステップを 1 つに（specs/029 T37）", () => {
  const render = (name: string, p: Partial<React.ComponentProps<typeof RunFlow>> = {}) => {
    const steps = stepsOf(name);
    return wrap(
      <RunFlow route={routeOf(steps)} flow={flowOf(steps)} steps={steps as unknown as ToolCall[]} variant="timeline" onSelect={() => {}} {...p} />,
    );
  };
  const slice = (html: string, a: string, b: string) => html.slice(html.indexOf(a), html.indexOf(b));

  it("経路: 停留所の下にその段階のステップを置く（同じ順を 2 度並べない。末尾の「システムの処理」も無い）", () => {
    const html = render("gap");
    expect(html).not.toContain("システムの処理");
    expect(html).not.toContain("data-stage"); // 段階ごとの別の一覧は出さない
    const inv1 = slice(html, 'data-stop="investigate-1"', 'data-stop="review-1"');
    expect(inv1).toContain("モデルの応答");
    const review1 = slice(html, 'data-stop="review-1"', 'data-stop="investigate-2"');
    expect(review1).toMatch(/data-edge="send_back"[^>]*>差し戻し</);
  });

  it("経路: 段階に時間のある行が 1 つなら、時間は見出しだけ（行には重ねない）", () => {
    const html = render("answer");
    const understand = slice(html, 'data-stop="understand-1"', 'data-stop="primer_search-1"');
    expect(understand.match(/10ms/g)).toHaveLength(1);
  });

  it("経路: 確定の後に「回答を送信」と所要時間", () => {
    const html = render("answer", { durationMs: 2790 });
    expect(html.indexOf("data-sent")).toBeGreaterThan(html.indexOf('data-stop="finalize-1"'));
    expect(html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ")).toContain("回答を送信 2.79s");
  });

  it("グラフ: 図の下に段階ごとの一覧。節点で絞ると、その段階だけ", () => {
    const html = render("gap", { defaultView: "graph", selected: "review" });
    const order = [...html.matchAll(/data-stage="([^"]+)"/g)].map((m) => m[1]);
    expect(order).toEqual(["review-1", "review-2"]);
  });
});

describe("カードの見方（利用者の設定。specs/029 T38）", () => {
  const render = (name: string, p: Partial<React.ComponentProps<typeof RunFlow>> = {}) => {
    const steps = stepsOf(name);
    return wrap(<RunFlow route={routeOf(steps)} flow={flowOf(steps)} steps={steps as unknown as ToolCall[]} variant="card" onSelect={() => {}} {...p} />);
  };

  it("経路（停留所の列）の下に、経路の順でカードを並べ、システムの処理はその段階のすぐ後に", () => {
    const html = render("gap", { durationMs: 3000 });
    const order = [...html.matchAll(/data-stage="([^"]+)"/g)].map((m) => m[1]);
    expect(order.indexOf("investigate-1")).toBeLessThan(order.indexOf("review-1"));
    expect(order.indexOf("review-1")).toBeLessThan(order.indexOf("investigate-2"));
    expect(html).not.toContain("システムの処理");
    expect(html).toContain("data-sent-line");
  });

  it("停留所を押すと、その段階のカードだけ", () => {
    const html = render("gap", { selected: "review-1" });
    expect([...html.matchAll(/data-stage="([^"]+)"/g)].map((m) => m[1])).toEqual(["review-1"]);
  });

  it("カードの左の列に段階の名前（周回も）。経路が長く縦になるときは、上の経路の列を出さない", () => {
    const off: FlowStep = {
      id: "system-followups", name: "system", status: "done", durationMs: 0,
      input: { kind: "followups" }, output: { skipped: "user_setting" }, node: "followups",
    };
    const steps = [...stepsOf("gap"), off];
    const html = wrap(
      <RunFlow route={routeOf(steps)} flow={flowOf(steps)} steps={steps as unknown as ToolCall[]} variant="card" durationMs={3000} onSelect={() => {}} />,
    );
    expect(html).not.toMatch(/data-stop=/); // 9 つ（送信を含む）なので経路の列は出さない
    const inv2 = html.slice(html.indexOf('data-stage="investigate-2"'));
    expect(inv2.replace(/<[^>]+>/g, " ")).toMatch(/^[^]*?調査（2 周目）/);
  });

  it("段階の中は起きた順（モデルの応答 → それが選んだ検索）", () => {
    for (const variant of ["card", "timeline"] as const) {
      const steps = stepsOf("tool_then_answer");
      const html = wrap(<RunFlow route={routeOf(steps)} flow={flowOf(steps)} steps={steps as unknown as ToolCall[]} variant={variant} />);
      const model = html.indexOf('data-step="system-model-1"');
      const search = html.search(/data-step="(?!system|primer|understand)[^"]+"/);
      expect(model, variant).toBeGreaterThan(-1);
      expect(model, variant).toBeLessThan(search);
    }
  });
});

