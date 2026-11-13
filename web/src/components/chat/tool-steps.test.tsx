import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ToolSteps, systemFieldValue } from "@/components/chat/tool-steps";
import { LocaleProvider } from "@/i18n/context";
import { ja } from "@/i18n/locales/ja";
import type { ToolCall } from "@/lib/types";

function step(p: Partial<ToolCall>): ToolCall {
  return { id: "x", name: "retrieve", label: "検索", status: "done", durationMs: 10, input: {}, output: null, summary: "", ...p };
}

function render(steps: ToolCall[]) {
  return renderToStaticMarkup(
    <LocaleProvider locale="ja" dict={ja}>
      <ToolSteps steps={steps} variant="card" expandedMap={{}} onToggleStep={() => {}} />
    </LocaleProvider>,
  );
}

describe("ToolSteps（システムの処理）", () => {
  const steps = [
    step({ id: "sys-1", name: "system", label: "ツールの使用を必須に", input: { kind: "force_tool" } }),
    step({ id: "s", name: "retrieve", label: "検索", summary: "資料 6 件" }),
    step({ id: "sys-2", name: "system", label: "回答の整形", input: { kind: "citation_cleanup" } }),
  ];

  it("システムの処理は流れの行にせず、末尾の 1 組に件数と名前だけを出す", () => {
    const html = render(steps);
    expect(html).toContain("システムの処理");
    expect(html).toContain("2 件");
    expect(html).toContain("ツールの使用を必須に・回答の整形");
    // 畳んだ組は閉じている（行の中身はまだ出さない）
    expect(html).toMatch(/aria-expanded="false"[^>]*>(?:(?!<\/button>)[\s\S])*システムの処理/);
    // エージェントの段階は先に並ぶ
    expect(html.indexOf("資料 6 件")).toBeLessThan(html.indexOf("システムの処理"));
  });

  it("システムの処理が無ければ組を出さない", () => {
    expect(render([steps[1]!])).not.toContain("システムの処理");
  });
});

describe("systemFieldValue（システムの処理の値）", () => {
  it("内訳から確かめた数字は式として読める形にする", () => {
    expect(
      systemFieldValue([
        { value: "135", op: "sum", from: ["30", "25", "80"] },
        { value: "55", op: "diff", from: ["80", "25"] },
      ]),
    ).toBe("135 = 30 + 25 + 80, 55 = 80 − 25");
    expect(systemFieldValue([])).toBe("—");
    expect(systemFieldValue(["12", "34"])).toBe("12, 34");
    expect(systemFieldValue(3)).toBe("3");
  });
});
