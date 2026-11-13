import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { TableResult } from "@/components/chat/tool-steps";
import { ja } from "@/i18n/locales/ja";

const render = (output: Record<string, unknown>) => renderToStaticMarkup(<TableResult output={output} t={ja} />);

describe("表の集計の表示（specs/028 R10）", () => {
  const output = {
    result: "表「部品台帳」（8 行）。条件 `在庫 < 発注点` に合う行: 2 行。…",
    rows_total: 8,
    rows_matched: 2,
    columns: ["部品番号", "在庫", "計算"],
    rows: [["P-1042", "6", "73600"], ["P-2011", "9", "11940"]],
    compute_label: "計算（(発注点 - 在庫) * 単価）",
    aggregates: {
      "計算（(発注点 - 在庫) * 単価）": { sum: "85540", avg: "42770", max: "73600", min: "11940" },
      在庫: { sum: "15", avg: "7.5", max: "9", min: "6" },
    },
  };

  it("該当行の表・行数・compute の列の集計を見せ、ほかの列は「すべての集計」に閉じて入れる", () => {
    const html = render(output);
    expect(html).toContain("P-1042");
    expect(html).toContain("該当 2 行 / 全 8 行");
    expect(html).toContain("85540");
    expect(html).toMatch(/<details[^>]*><summary[^>]*>すべての集計/);
    expect(html).not.toMatch(/<details[^>]*open/);
    // 先に見せる集計に、ほかの列（在庫）は入れない
    expect(html.split("<details")[0]).not.toContain("7.5");
    expect(html.split("<details")[1]).toContain("7.5");
  });

  it("集計関数の値はそのまま出す", () => {
    const html = render({ ...output, compute_label: "計算（max(単価)）", compute_value: "24800", aggregates: {} });
    expect(html).toContain("計算（max(単価)）");
    expect(html).toContain("24800");
    expect(html).not.toContain("<details");
  });

  it("構造の無い古い記録は今の文のまま出す", () => {
    const html = render({ result: "表（4 行）。全行: 4 行。\n| 部品 | 在庫 |\n|---|---|\n| P-1 | 6 |" });
    expect(html).toContain("表（4 行）。全行: 4 行。");
    expect(html).toContain("<table");
    expect(html).not.toContain("該当");
  });

  it("表の注記（「注:」の行）は行数に数えず、注記として見せる（specs/026 T30）", () => {
    const html = render({ ...output, notes: ["注: 在庫が発注点を下回ったら、資材係が発注する。"] });
    expect(html).toContain("表の注記");
    expect(html).toContain("注: 在庫が発注点を下回ったら");
    expect(render(output)).not.toContain("表の注記");
  });
});
