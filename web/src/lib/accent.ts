/**
 * アクセント色ごとの「読める」色合い。
 * 朱は既定の色のままで、明るい地の文字・白い文字の下地として 4.6:1 前後になるよう作ってある。
 * ほかの色（橙・緑・青・紫）は元の色のままだと明るすぎて、白い地の文字も白い文字の下地も 3〜3.9:1 しか無い。
 * そこで色相を保ったまま、朱と同じ読みやすさになるよう明るさだけを合わせた値を持つ。
 *
 * - ink:    明るいテーマの文字・枠と、両テーマの塗り（白い文字を載せる）。白に対して 4.6:1 以上
 * - bright: 暗いテーマの文字・枠・小さな印。一番明るい面（surface-elev）に対して 4.5:1 以上
 *
 * 値は OKLCH で明るさを動かして求めた（lib/accent.test.ts でコントラストを確かめる）。
 * 一覧に無い色が保存されていたときは CSS の既定（globals.css の :root）に任せる。
 */
import { ACCENT_PRESETS } from "@/lib/constants";

export type AccentTone = { ink: string; bright: string };

export const ACCENT_TONES: Record<(typeof ACCENT_PRESETS)[number], AccentTone> = {
  "#D2402B": { ink: "#d2402b", bright: "#e06c58" }, // 朱
  "#D97757": { ink: "#b75a3b", bright: "#d97757" }, // 橙
  "#3FA77E": { ink: "#11855e", bright: "#3fa77e" }, // 緑
  "#3D7EE6": { ink: "#3272d8", bright: "#558eea" }, // 青
  "#8B6FE0": { ink: "#7e62d0", bright: "#9680e5" }, // 紫
};

export function accentTone(accent: string): AccentTone | undefined {
  const key = ACCENT_PRESETS.find((p) => p.toLowerCase() === accent.toLowerCase());
  return key ? ACCENT_TONES[key] : undefined;
}

/** <html> に当てる CSS 変数。一覧に無い色では ink・bright を消し、CSS の既定の式に任せる */
export function accentVars(accent: string): Record<string, string | null> {
  const tone = accentTone(accent);
  return { "--accent": accent, "--accent-ink": tone?.ink ?? null, "--accent-bright": tone?.bright ?? null };
}
