import { describe, expect, it } from "vitest";
import { ACCENT_PRESETS } from "@/lib/constants";
import { ACCENT_TONES, accentTone, accentVars } from "@/lib/accent";

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

describe("アクセント色の読める色合い", () => {
  it("すべての色に値がある", () => {
    for (const p of ACCENT_PRESETS) expect(ACCENT_TONES[p]).toBeDefined();
  });
  it.each(ACCENT_PRESETS)("%s: 明るい地の文字と白い文字の下地として読める", (p) => {
    const { ink } = ACCENT_TONES[p];
    expect(contrast(ink, "#ffffff")).toBeGreaterThanOrEqual(4.5);
    expect(contrast(ink, "#f5f4f1")).toBeGreaterThanOrEqual(4.1);
  });
  it.each(ACCENT_PRESETS)("%s: 暗い地の文字として読める", (p) => {
    const { bright } = ACCENT_TONES[p];
    // 一番明るい面（--surface-elev）でも読める
    expect(contrast(bright, "#26282d")).toBeGreaterThanOrEqual(4.5);
  });
  it("朱は今の見た目のまま", () => {
    expect(ACCENT_TONES["#D2402B"]).toEqual({ ink: "#d2402b", bright: "#e06c58" });
  });
  it("大文字・小文字を区別しない。一覧に無い色は CSS の既定に任せる", () => {
    expect(accentTone("#3fa77e")).toBe(ACCENT_TONES["#3FA77E"]);
    expect(accentVars("#123456")).toEqual({ "--accent": "#123456", "--accent-ink": null, "--accent-bright": null });
  });
});
