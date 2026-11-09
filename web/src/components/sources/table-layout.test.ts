import { describe, expect, it } from "vitest";
import { parseTableHtml } from "@/components/sources/parse-table-html";
import { markdownTableToHtml } from "@/components/sources/parse-section-body";
import { cellFit, columnCount, numericColumns } from "@/components/sources/table-layout";

const md = (rows: string[]) => parseTableHtml(markdownTableToHtml(rows))!;

describe("table-layout", () => {
  const model = md([
    "| 設備ID | 振動 | 温度 | 暫定判定 | 補足 |",
    "|---|---|---|---|---|",
    "| MX-17 | 0.91 | 86.4℃ | 停止候補 | 軸受け交換が必要で、部品は翌営業日AMに到着する |",
    "| MX-21 | 1,200 | 42 L/min | 監視継続 | 圧力変動あり |",
  ]);

  it("数値・短い語・長い文を見分ける", () => {
    const [id, vib, temp, judge, note] = model.rows[1].cells;
    expect([cellFit(id), cellFit(vib), cellFit(temp), cellFit(judge), cellFit(note)]).toEqual([
      "short",
      "numeric",
      "numeric",
      "short",
      "long",
    ]);
  });

  it("本文がすべて数値の列だけを右寄せの対象にする（見出しは数えない）", () => {
    expect([...numericColumns(model)]).toEqual([1, 2]);
    expect(columnCount(model)).toBe(5);
  });

  it("結合セルのある表は判定しない", () => {
    const merged = parseTableHtml('<table><tr><td colspan="2">A</td></tr><tr><td>1</td><td>2</td></tr></table>')!;
    expect(numericColumns(merged).size).toBe(0);
  });
});
