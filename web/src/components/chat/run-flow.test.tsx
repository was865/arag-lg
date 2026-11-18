import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { FlowRail, RunFlow } from "@/components/chat/run-flow";
import { GraphView } from "@/components/chat/graph-view";
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

  it("いつもの経路（そのまま通過）と実行中は、見出しにひと言を足さない（停留所の印で分かる）", () => {
    const t = text(wrap(<RunFlow route={routeOf(stepsOf("answer"))} />));
    expect(t).toContain("グラフの実行経路");
    expect(t).not.toContain("確認をそのまま通過");
    const live = text(wrap(<RunFlow route={routeOf(stepsOf("gap"), { running: true })} running />));
    expect(live).not.toContain("書き直して通過");
  });

  it("停留所の名前に、その段階の説明を添える（ホバーで読める）", () => {
    const html = wrap(<RunFlow route={routeOf(stepsOf("answer"))} />);
    expect(html).toContain('title="調べ残し・表の集計・数字を確かめ');
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

describe("RunFlow のグラフの特徴（specs/029 T32）", () => {
  const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

  it("確定の後に「回答を送信」と run の所要時間を置く（実行中は置かない）", () => {
    const route = routeOf(stepsOf("answer"));
    expect(text(wrap(<RunFlow route={route} durationMs={3120} />))).toContain("回答を送信 3.12s");
    expect(text(wrap(<RunFlow route={route} durationMs={3120} running />))).not.toContain("回答を送信");
  });

  it("条件つきの辺は、いつもと違う分岐（差し戻し・雑談など）だけ札を書く", () => {
    const html = wrap(<RunFlow route={routeOf(stepsOf("gap"))} durationMs={1000} />);
    expect(html).toContain('data-edge="send_back"');
    // いつもの分岐（資料・通過）は札を書かない（停留所の印で分かる）
    expect(html).not.toContain('data-edge="docs"');
    expect(html).not.toContain('data-edge="pass"');
    expect(wrap(<RunFlow route={routeOf(stepsOf("chat"))} />)).toContain('data-edge="chat"');
  });

  it("経路とグラフ全体を切り替えられる", () => {
    const html = wrap(<RunFlow route={routeOf(stepsOf("answer"))} flow={flowOf(stepsOf("answer"))} />);
    expect(text(html)).toContain("経路");
    expect(text(html)).toContain("グラフ全体");
  });
});

describe("GraphView（グラフ全体の弧線図。specs/029 T33）", () => {
  const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
  const view = (name: string) => wrap(<GraphView flow={flowOf(stepsOf(name))} route={routeOf(stepsOf(name))} />);

  it("すべての節点を並べ、通った回数と通らなかった節点を示す", () => {
    const t = text(view("gap"));
    for (const label of ["画像", "理解", "最初の検索", "調査", "見張り", "確認", "確定", "続けて聞く"]) expect(t).toContain(label);
    expect(t).toContain("×2"); // 差し戻しで調査を 2 回通った
    expect(t).toContain("通らず"); // 画像
  });

  it("通った辺と通らなかった辺を分け、戻る辺には回数を添える", () => {
    const html = view("gap");
    expect(html).toMatch(/data-edge="send_back" data-taken="1"/);
    expect(html).toMatch(/data-edge="chat" data-taken="0"/);
    expect(text(html)).toContain("差し戻し ×1");
  });

  it("たどり直しのトークンと「もう一度たどる」を出す", () => {
    const html = view("answer");
    expect(html).toContain("<animateMotion");
    expect(text(html)).toContain("もう一度たどる");
    expect(html).toContain("ar-trace");
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
