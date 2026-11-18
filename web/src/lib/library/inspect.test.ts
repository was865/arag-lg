import { describe, expect, it } from "vitest";
import { boxesOnPage, boxToRect, chunksOnPage, firstPageOf, warningsByPage, type ChunkOut, type ParseReport } from "./inspect";

const chunk = (over: Partial<ChunkOut>): ChunkOut =>
  ({ id: "c", boxes: [], page_start: null, page_end: null, ...over }) as unknown as ChunkOut;

describe("boxToRect", () => {
  it("BOTTOMLEFT は頁の高さで反転する", () => {
    // 高さ 800 の頁で、下から 680〜700 の帯 → 上から 100〜120
    const r = boxToRect({ page: 1, bbox: [10, 700, 300, 680], origin: "BOTTOMLEFT" }, 800, 1);
    expect(r).toEqual({ left: 10, top: 100, width: 290, height: 20 });
  });
  it("TOPLEFT は反転しない", () => {
    const r = boxToRect({ page: 1, bbox: [10, 100, 300, 120], origin: "TOPLEFT" }, 800, 1);
    expect(r).toEqual({ left: 10, top: 100, width: 290, height: 20 });
  });
  it("倍率をかける", () => {
    const r = boxToRect({ page: 1, bbox: [10, 700, 300, 680], origin: "BOTTOMLEFT" }, 800, 2);
    expect(r).toEqual({ left: 20, top: 200, width: 580, height: 40 });
  });
});

describe("chunksOnPage", () => {
  const a = chunk({ id: "a", boxes: [{ page: 2, bbox: [0, 0, 1, 1] }] as never, page_start: 2, page_end: 3 });
  const b = chunk({ id: "b", page_start: 3, page_end: 4 });
  const c = chunk({ id: "c" });
  it("枠があれば枠の頁、無ければ頁の範囲", () => {
    expect(chunksOnPage([a, b, c], 2).map((x) => x.id)).toEqual(["a"]);
    expect(chunksOnPage([a, b, c], 3).map((x) => x.id)).toEqual(["b"]);
    expect(chunksOnPage([a, b, c], 4).map((x) => x.id)).toEqual(["b"]);
    expect(chunksOnPage([a, b, c], 1)).toEqual([]);
  });
  it("頁の枠だけ取り出す・最初の頁", () => {
    expect(boxesOnPage(a, 2)).toHaveLength(1);
    expect(boxesOnPage(a, 3)).toHaveLength(0);
    expect(firstPageOf(a)).toBe(2);
    expect(firstPageOf(b)).toBe(3);
    expect(firstPageOf(c)).toBeNull();
  });
});

describe("warningsByPage", () => {
  it("頁ごとにまとめ、頁の無い警告は null に入れる", () => {
    const report = {
      warnings: [
        { code: "empty_page", severity: "info", page: 2, message: "" },
        { code: "garbled_text", severity: "warn", page: 2, message: "" },
        { code: "no_text", severity: "warn", page: null, message: "" },
      ],
    } as unknown as ParseReport;
    const m = warningsByPage(report);
    expect(m.get(2)).toHaveLength(2);
    expect(m.get(null)).toHaveLength(1);
  });
});
