import { describe, expect, it } from "vitest";
import { changeViews } from "@/lib/chat/system-changes";

describe("changeViews（specs/033 R17）", () => {
  it("数の増減に向きを付ける", () => {
    const v = changeViews([
      { key: "P-1042", column: "現在庫", before: 15, after: 14 },
      { key: "P-1043", column: "現在庫", before: "3", after: "5" },
      { key: "P-1043", column: "発注点との比較", before: "下回っている", after: "満たしている" },
    ]);
    expect(v.map((x) => x.dir)).toEqual(["down", "up", null]);
    expect(v[0]).toMatchObject({ before: "15", after: "14", kind: "value" });
  });
  it("行の増減", () => {
    const v = changeViews([
      { key: "PO-1", column: null, change: "added" },
      { key: "PO-2", column: null, change: "removed" },
    ]);
    expect(v.map((x) => x.kind)).toEqual(["added", "removed"]);
  });
  it("配列でなければ空", () => {
    expect(changeViews(null)).toEqual([]);
  });
});
