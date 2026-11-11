import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { ACCENT_PRESETS, DEFAULT_ACCENT, THEME_COLOR_DARK, THEME_COLOR_LIGHT } from "@/lib/constants";

const css = readFileSync(join(__dirname, "../app/globals.css"), "utf8");

/** テーマのブロック（.theme-light / .theme-dark）から変数の値を読む */
function themeVar(theme: "light" | "dark", name: string): string {
  const block = css.slice(css.indexOf(`.theme-${theme} {`));
  const m = block.slice(0, block.indexOf("}")).match(new RegExp(`--${name}:\\s*([^;]+);`));
  if (!m) throw new Error(`.theme-${theme} に --${name} が無い`);
  return m[1].trim();
}

describe("テーマの色（specs/025 R40）", () => {
  it("ステータスバーの色は地の色と同じ", () => {
    expect(themeVar("light", "bg")).toBe(THEME_COLOR_LIGHT);
    expect(themeVar("dark", "bg")).toBe(THEME_COLOR_DARK);
  });
  it("既定のアクセントは朱で、CSS の既定値と同じ", () => {
    expect(DEFAULT_ACCENT).toBe("#D2402B");
    expect(ACCENT_PRESETS).toContain(DEFAULT_ACCENT);
    expect(css).toMatch(/--accent:\s*#d2402b;/i);
  });
  it("危険色は朱と別の色", () => {
    expect(themeVar("light", "danger").toLowerCase()).not.toBe(DEFAULT_ACCENT.toLowerCase());
  });
});
