import { describe, expect, it } from "vitest";
import { extractCitationNums, normalizeCitationMarkers } from "@/lib/citation-markers";

describe("citation marker utilities", () => {
  it("全角・隅付き括弧の引用番号を半角 [n] へ正規化する", () => {
    expect(normalizeCitationMarkers("結論【1】と補足［2］、既存 [3]")).toBe("結論[1]と補足[2]、既存 [3]");
  });

  it("資料タグをまねた [n=1] [資料 n=\"2\"] も番号として扱う（生成中の表示用）", () => {
    expect(normalizeCitationMarkers('A[n=1]B[資料 n="2"]C')).toBe("A[1]B[2]C");
    expect(extractCitationNums('x[n="7"]')).toEqual([7]);
  });

  it("対応するすべての引用記号から番号を抽出する", () => {
    expect(extractCitationNums("a【4】 b［12］ c[3]")).toEqual([4, 12, 3]);
  });
});
