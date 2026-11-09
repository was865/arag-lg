// 検索結果の強調（specs/022 R3）
import { describe, it, expect } from "vitest";
import { highlightParts } from "@/components/sidebar/sidebar-search-results";

describe("highlightParts", () => {
  it("語の当たる部分を奇数番目に分ける（大文字小文字を区別しない）", () => {
    expect(highlightParts("MX-17 の異常時", ["mx-17"])).toEqual(["", "MX-17", " の異常時"]);
  });
  it("複数の語と、正規表現の記号を含む語", () => {
    expect(highlightParts("内線 (2417) と 8月", ["(2417)", "8月"])).toEqual(["内線 ", "(2417)", " と ", "8月", ""]);
  });
  it("語が無ければそのまま", () => {
    expect(highlightParts("題名", [""])).toEqual(["題名"]);
  });
});
