import { describe, expect, it } from "vitest";
import { chunk, selectRange, toggleId } from "@/lib/library/selection";

describe("toggleId", () => {
  it("あれば外し、無ければ足す（元の集合は変えない）", () => {
    const a = new Set(["x"]);
    expect([...toggleId(a, "y")]).toEqual(["x", "y"]);
    expect([...toggleId(a, "x")]).toEqual([]);
    expect([...a]).toEqual(["x"]);
  });
});

describe("selectRange", () => {
  const order = ["a", "b", "c", "d", "e"];
  it("起点から対象までを（向きに関係なく）足す", () => {
    expect([...selectRange(new Set(["a"]), order, "b", "d")].sort()).toEqual(["a", "b", "c", "d"]);
    expect([...selectRange(new Set(), order, "d", "b")].sort()).toEqual(["b", "c", "d"]);
  });
  it("起点が一覧に無ければ対象だけ", () => {
    expect([...selectRange(new Set(), order, "zz", "c")]).toEqual(["c"]);
    expect([...selectRange(new Set(), order, null, "c")]).toEqual(["c"]);
  });
});

describe("chunk", () => {
  it("上限ごとに分ける", () => {
    expect(chunk([1, 2, 3, 4, 5], 2)).toEqual([[1, 2], [3, 4], [5]]);
    expect(chunk([], 2)).toEqual([]);
  });
});
