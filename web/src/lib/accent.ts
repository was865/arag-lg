/**
 * アクセント色ごとの「読める」色合い。
 * 朱は明るい地の文字・白い文字の下地として 4.6:1 前後になるよう作ってある。藍・常磐も同じ明るさ
 * （OKLCH の L ≒ 0.55）にそろえ、彩度は朱より抑えて紙の地に馴染ませた。ink はそのまま元の色でもある。
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
  "#4A76AE": { ink: "#4a76ae", bright: "#6592cc" }, // 藍
  "#438067": { ink: "#438067", bright: "#5f9c82" }, // 常磐
};

/** 以前選べた色（橙・緑・青・紫）。保存されていたら近い色へ移す */
export const RETIRED_ACCENTS: Record<string, (typeof ACCENT_PRESETS)[number]> = {
  "#d97757": "#D2402B", // 橙 → 朱
  "#3fa77e": "#438067", // 緑 → 常磐
  "#3d7ee6": "#4A76AE", // 青 → 藍
  "#8b6fe0": "#4A76AE", // 紫 → 藍
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
