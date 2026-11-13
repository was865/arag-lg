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

describe("RunFlow（実際にたどった順の流れ。specs/029 R7〜R9）", () => {
  const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

  it("差し戻しは 2 周目として続けて並べ、理由と見出しのひと言を出す（×2 にまとめない）", () => {
    const html = wrap(<RunFlow route={routeOf(stepsOf("gap"))} onSelect={() => {}} />);
    const t = text(html);
    expect(t).toContain("確認で 1 回差し戻し、書き直して通過");
    expect(t).toMatch(/確認 差し戻し\s+調べ残し/);
    expect(t).toContain("調査（2 周目）");
    expect(t).toContain("確認（2 周目） 通過");
    expect(html).not.toContain("×2");
  });

  it("そのまま通過した回答は、見出しでそう言う", () => {
    expect(text(wrap(<RunFlow route={routeOf(stepsOf("answer"))} />))).toContain("確認をそのまま通過");
  });

  it("下書きへの退避は見張りの停留所で示す", () => {
    const t = text(wrap(<RunFlow route={routeOf(stepsOf("rewrite_reply_uses_draft"))} />));
    expect(t).toContain("書き直しを取り消し → 下書きへ");
    expect(t).toContain("書き直しを取り消し、確認前の下書きを回答に");
  });

  it("節点の名前の無い古い記録は、推定を含むことを示す", () => {
    expect(wrap(<RunFlow route={routeOf(stepsOf("answer"))} />)).toContain("古い記録のため一部は推定です");
  });

  it("絞っている停留所に印を付け、周回つきの名前と解除を出す", () => {
    const route = routeOf(stepsOf("gap"));
    const html = wrap(<RunFlow route={route} selected="investigate-2" onSelect={() => {}} />);
    expect(html).toContain('aria-pressed="true"');
    expect(text(html)).toContain("調査（2 周目）のステップだけを表示中");
    expect(html).toContain("解除");
  });

  it("長い経路（9 つ以上）は縦に並べる（横一列の指定を付けない）", () => {
    const route = routeOf(stepsOf("gap_then_numbers"));
    expect(route.stops.length).toBeGreaterThan(8);
    expect(wrap(<RunFlow route={route} />)).not.toContain("@[480px]:flex-row");
    expect(wrap(<RunFlow route={routeOf(stepsOf("answer"))} />)).toContain("@[480px]:flex-row");
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
