import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { FlowRail, RunFlow } from "@/components/chat/run-flow";
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

describe("RunFlow（グラフの実行経路の図。specs/029 R7・T34）", () => {
  const text = (html: string) => html.replace(/<title>[^<]*<\/title>/g, " ").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
  const view = (name: string, p: Partial<React.ComponentProps<typeof RunFlow>> = {}) =>
    wrap(<RunFlow route={routeOf(stepsOf(name))} flow={flowOf(stepsOf(name))} {...p} />);

  it("見出しは「グラフの実行経路」。ひと言の要約はいつもと違う経路だけ", () => {
    expect(text(view("answer"))).toContain("グラフの実行経路");
    expect(text(view("answer"))).not.toContain("確認をそのまま通過");
    expect(text(view("gap"))).toContain("確認で 1 回差し戻し、書き直して通過");
    expect(text(view("gap", { running: true }))).not.toContain("書き直して通過");
  });

  it("同じ図を横と縦の 2 つの向きで持ち、すべての節点を並べる", () => {
    const html = view("answer");
    expect(html).toContain('data-orient="row"');
    expect(html).toContain('data-orient="column"');
    for (const id of ["read_image", "understand", "primer_search", "investigate", "guard", "review", "finalize", "followups"])
      expect(html).toContain(`data-node="${id}"`);
  });

  it("通った辺と通らなかった辺を分け、札はいつもと違う分岐だけに書く", () => {
    const html = view("gap");
    expect(html).toMatch(/data-edge="send_back" data-taken="1"/);
    expect(html).toMatch(/data-edge="chat" data-taken="0"/);
    expect(text(html)).toContain("差し戻し ×1");
    // いつもの分岐（資料・通過）は札を書かない（ホバーの説明だけ）
    expect(text(html)).not.toContain("資料");
    expect(text(view("chat"))).toContain("雑談");
  });

  it("節点の下に何をしたかを 1 行、何度も通った節点に ×n、ホバーで説明と周回の内訳", () => {
    const html = view("gap");
    expect(text(html)).toContain("×2");
    expect(html).toMatch(/<title>確認 — [^<]*1 周目: 差し戻し/);
  });

  it("確定の後に「送信」と所要時間の印を置く（実行中は置かない）。朱はこの印だけ", () => {
    expect(text(view("answer", { durationMs: 3120 }))).toContain("送信 3.12s");
    expect(view("answer", { durationMs: 3120, running: true })).not.toContain("data-sent");
    expect(view("answer", { durationMs: 3120 }).match(/fill-accent/g)).toHaveLength(2); // 横と縦の送信の印
  });

  it("節点を押すと、その節点で絞る（押せるのはステップのある節点だけ）", () => {
    const html = view("gap", { selected: "review", onSelect: () => {} });
    expect(html).toMatch(/data-node="review" role="button" tabindex="0" aria-pressed="true"/);
    expect(html).not.toMatch(/data-node="read_image" role="button"/);
    expect(text(html)).toContain("確認のステップだけを表示中");
  });

  it("続けて聞くを作らなかったときは、通らなかった節点に「設定でオフ」と書く", () => {
    const off: FlowStep = {
      id: "system-followups", name: "system", status: "done", durationMs: 0,
      input: { kind: "followups" }, output: { skipped: "user_setting" }, node: "followups",
    };
    const steps = [...stepsOf("answer"), off];
    const html = wrap(<RunFlow route={routeOf(steps)} flow={flowOf(steps)} durationMs={1000} />);
    expect(text(html)).toContain("設定でオフ");
    expect(html).toMatch(/data-edge="followups" data-taken="0"/);
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
