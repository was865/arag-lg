import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { DURATION, EASE, stackStyle } from "@/lib/motion";

const css = readFileSync(join(__dirname, "../app/globals.css"), "utf8");

/** globals.css の @theme から変数の値を読む */
function cssVar(name: string): string {
  const m = css.match(new RegExp(`--${name}:\\s*([^;]+);`));
  if (!m) throw new Error(`--${name} が globals.css に無い`);
  return m[1].trim();
}

describe("動きの値", () => {
  it("時間は 3 段で、CSS と同じ値", () => {
    expect(cssVar("duration-fast")).toBe(`${DURATION.fast * 1000}ms`);
    expect(cssVar("duration-mid")).toBe(`${DURATION.mid * 1000}ms`);
    expect(cssVar("duration-slow")).toBe(`${DURATION.slow * 1000}ms`);
  });
  it("曲線は CSS と同じ値", () => {
    for (const k of ["spring", "out", "in"] as const) {
      expect(cssVar(`ease-${k}`)).toBe(`cubic-bezier(${EASE[k].join(", ")})`);
    }
  });
  it("消える時間は出る時間より短い", () => {
    expect(DURATION.exit).toBeLessThan(DURATION.mid);
  });
});

describe("stackStyle（トーストの束）", () => {
  it("いちばん新しいものは手前に原寸で出る", () => {
    expect(stackStyle(0, false)).toEqual({ y: 0, scale: 1, opacity: 1, hidden: false });
  });
  it("古いものほど上へずれて縮み、薄くなる", () => {
    const a = stackStyle(1, false);
    const b = stackStyle(2, false);
    expect(a.y).toBeLessThan(0);
    expect(b.y).toBeLessThan(a.y);
    expect(b.scale).toBeLessThan(a.scale);
    expect(b.opacity).toBeLessThan(a.opacity);
  });
  it("4 件目以降は隠す", () => {
    expect(stackStyle(3, false)).toMatchObject({ opacity: 0, hidden: true });
  });
  it("広げると全部を原寸で縦に並べる", () => {
    expect(stackStyle(3, true, 48)).toEqual({ y: -(48 + 8) * 3, scale: 1, opacity: 1, hidden: false });
  });
});
