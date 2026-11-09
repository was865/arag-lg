import { describe, expect, it } from "vitest";
import { compact, formatDuration, formatRate, niceMax, reasonLabel, tagLabel, tickDates } from "./analytics";

describe("analytics helpers", () => {
  it("compact は 1 万未満を区切り、以上を K/M で縮める", () => {
    expect(compact(0)).toBe("0");
    expect(compact(1284)).toBe("1,284");
    expect(compact(12900)).toBe("12.9K");
    expect(compact(4_200_000)).toBe("4.2M");
  });

  it("formatRate は割合を % で、無いときは —", () => {
    expect(formatRate(0.876)).toBe("87.6%");
    expect(formatRate(1)).toBe("100%");
    expect(formatRate(null)).toBe("—");
  });

  it("formatDuration は秒（1 分以上は分と秒）", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(850)).toBe("0.9 秒");
    expect(formatDuration(12_340)).toBe("12.3 秒");
    expect(formatDuration(75_000)).toBe("1 分 15 秒");
  });

  it("niceMax はきりのよい上限を返す", () => {
    expect(niceMax(0)).toBe(4);
    expect(niceMax(3)).toBe(4);
    expect(niceMax(7)).toBe(8);
    expect(niceMax(13)).toBe(20);
    expect(niceMax(130)).toBe(200);
  });

  it("tickDates は先頭と末尾を含み、等間隔に間引く", () => {
    const d = Array.from({ length: 30 }, (_, i) => `2026-10-${String(i + 1).padStart(2, "0")}`);
    const t = tickDates(d, 6);
    expect(t[0]).toBe(d[0]);
    expect(t.at(-1)).toBe(d[29]);
    expect(t.length).toBeLessThanOrEqual(7);
    expect(tickDates(d.slice(0, 7), 7)).toEqual(d.slice(0, 7));
  });

  it("理由とタグは日本語ラベル、未知の値はそのまま", () => {
    expect(reasonLabel("no_sources")).toBe("資料が見つからない");
    expect(reasonLabel("x")).toBe("x");
    expect(tagLabel("outdated")).toBe("情報が古い");
  });
});
