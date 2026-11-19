import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { FollowupRows, Followups, followupsFor, followupsPending, isClarify } from "@/components/chat/followups";
import { SystemFields } from "@/components/chat/tool-steps/system-fields";
import { LocaleProvider } from "@/i18n/context";
import { ja } from "@/i18n/locales/ja";
import { newTurn } from "@/lib/chat/turn";
import type { Turn } from "@/lib/types";

function render(node: React.ReactNode) {
  return renderToStaticMarkup(
    <LocaleProvider locale="ja" dict={ja}>
      {node}
    </LocaleProvider>,
  );
}

function done(p: Partial<Turn> = {}): Turn {
  return { ...newTurn("質問"), status: "done", streaming: false, answer: "回答", suggestions: ["次の質問 A", "次の質問 B"], ...p };
}

describe("Followups（続けて聞く、specs/028 R6）", () => {
  it("見出しと候補の行をボタンで出し、50ms ずつずらして現れる", () => {
    const html = render(<Followups items={["在庫の推移は？", "発注点の決め方は？"]} onSend={() => {}} />);
    expect(html).toContain("続けて聞く");
    expect(html.match(/<button/g)).toHaveLength(2);
    expect(html).toContain("↳");
    expect(html).toContain("在庫の推移は？");
    expect(html).toContain("animation-delay:50ms");
    expect(html).toContain("motion-reduce:animate-none");
  });

  it("作っているあいだは見出しと骨組みを出す（読み上げには作成中と伝える）", () => {
    const html = render(<Followups items={[]} pending onSend={() => {}} />);
    expect(html).toContain("続けて聞く");
    expect(html).toContain('aria-busy="true"');
    expect(html).not.toContain("<button");
  });

  it("最大 3 行・候補が無ければ何も出さない", () => {
    expect(render(<Followups items={["1", "2", "3", "4"]} onSend={() => {}} />).match(/<button/g)).toHaveLength(3);
    expect(render(<Followups items={[]} onSend={() => {}} />)).toBe("");
  });

  it("押すと文をそのまま送る", () => {
    const sent: string[] = [];
    const el = FollowupRows({ items: ["次は？"], onSend: (q) => sent.push(q) }) as React.ReactElement<{ children: React.ReactNode }>;
    // ul → li → button の onClick を呼ぶ
    const find = (n: React.ReactNode): (() => void) | undefined => {
      if (!n || typeof n !== "object") return undefined;
      if (Array.isArray(n)) {
        for (const c of n) {
          const f = find(c);
          if (f) return f;
        }
        return undefined;
      }
      const e = n as React.ReactElement<{ onClick?: () => void; children?: React.ReactNode }>;
      if (e.type === "button" && e.props.onClick) return e.props.onClick;
      return find(e.props?.children);
    };
    find(el)?.();
    expect(sent).toEqual(["次は？"]);
  });
});

describe("聞き返し（specs/031）", () => {
  it("聞き返しで終わったターンは、選択肢の見出しで出す", () => {
    const ask = { id: "c1", name: "ask_user", label: "聞き返し", status: "done", input: { question: "どれ？" } };
    const turn = done({ steps: [ask] as unknown as Turn["steps"] });
    expect(isClarify(turn)).toBe(true);
    expect(isClarify(done())).toBe(false);
    const sys = { id: "system-clarify", name: "system", label: "聞き返しで終える", status: "done", input: { kind: "clarify" } };
    expect(isClarify(done({ steps: [sys] as unknown as Turn["steps"] }))).toBe(true);
    const html = render(<Followups items={["第5章の内容"]} clarify onSend={() => {}} />);
    expect(html).toContain(ja.chat.clarifyTitle);
    expect(html).not.toContain(ja.chat.followupsTitle);
  });
});

describe("followupsFor（出すかどうか）", () => {
  it("最後のターン・完了・候補あり・実行中でないときだけ出す", () => {
    expect(followupsFor(done(), true, false)).toEqual(["次の質問 A", "次の質問 B"]);
    expect(followupsFor(done(), false, false)).toEqual([]);
    expect(followupsFor(done(), true, true)).toEqual([]);
    expect(followupsFor(done({ status: "cancelled" }), true, false)).toEqual([]);
    expect(followupsFor(done({ suggestions: undefined }), true, false)).toEqual([]);
  });

  it("作っている最中かは、最後のターン・完了・実行中でないときだけ見る", () => {
    expect(followupsPending(done({ suggestions: [], followupsPending: true }), true, false)).toBe(true);
    expect(followupsPending(done({ suggestions: [], followupsPending: true }), false, false)).toBe(false);
    expect(followupsPending(done({ suggestions: [], followupsPending: true }), true, true)).toBe(false);
    expect(followupsPending(done({ suggestions: [] }), true, false)).toBe(false);
  });
});

describe("followups の記録の表示", () => {
  it("入力・出力の項目を読める名前で出す", () => {
    const html = render(
      <SystemFields data={{ kind: "followups", model: "gemma4-12b", titles: ["規程.pdf"], ms: 812, questions: ["次は？"] }} t={ja} />,
    );
    for (const label of ["モデル", "引用した資料", "かかった時間（ms）", "候補"]) expect(html).toContain(label);
    // 落とした候補は「候補（理由）」で読めるようにする（T15）
    const dropped = render(
      <SystemFields data={{ kind: "followups", history_turns: 2, dropped: [{ question: "在庫数は？", reason: "これまでの質問と同じ" }] }} t={ja} />,
    );
    expect(dropped).toContain("落とした候補");
    expect(dropped).toContain("在庫数は？（これまでの質問と同じ）");
    expect(dropped).toContain("渡した前のターンの数");
    // 利用者の設定で作らなかった（specs/028 R7）
    const skipped = render(<SystemFields data={{ kind: "followups", skipped: "user_setting" }} t={ja} />);
    expect(skipped).toContain("作らなかった理由");
    expect(skipped).toContain("利用者の設定でオフ");
  });
});
