import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { FlowRail, RunFlow } from "@/components/chat/run-flow";
import { flowOf, type FlowNodeId, type FlowStep } from "@/lib/chat/flow";
import { LocaleProvider } from "@/i18n/context";
import { ja } from "@/i18n/locales/ja";

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

const wrap = (el: React.ReactNode) =>
  renderToStaticMarkup(
    <LocaleProvider locale="ja" dict={ja}>
      {el}
    </LocaleProvider>,
  );

describe("RunFlow（回答の流れ。specs/029 R7〜R9）", () => {
  it("差し戻しは弧の札で回数を出し、調査・見張り・確認に ×2 を付ける", () => {
    const html = wrap(<RunFlow flow={flowOf(stepsOf("gap"))} onSelect={() => {}} />);
    expect(html).toContain("差し戻し 1 回");
    expect(html.match(/×2/g)?.length).toBe(3);
    // 画像の無いターンは画像の札を並べない
    expect(html).not.toContain(">画像<");
  });

  it("下書きへの退避は札で示す", () => {
    const html = wrap(<RunFlow flow={flowOf(stepsOf("rewrite_reply_uses_draft"))} />);
    expect(html).toContain("下書きへ");
  });

  it("節点の名前の無い古い記録は、推定であることを示す", () => {
    expect(wrap(<RunFlow flow={flowOf(stepsOf("answer"))} />)).toContain("古い記録のため、流れは推定です");
  });

  it("絞っている節点に輪郭を付け、解除を出す", () => {
    const html = wrap(<RunFlow flow={flowOf(stepsOf("answer"))} selected={"review" as FlowNodeId} onSelect={() => {}} />);
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain("確認のステップだけを表示中");
    expect(html).toContain("解除");
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
