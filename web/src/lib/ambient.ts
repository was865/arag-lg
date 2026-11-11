/** 首ページの漂う光と、カードの傾きの計算（specs/025 見直し: Canvas と 3D は控えめに、意味のある所だけ）。 */

export type Rgb = [number, number, number];

/** "#RRGGBB" → [r, g, b]。読めない値は null（そのときは光を描かない）。 */
export function hexToRgb(hex: string): Rgb | null {
  const m = hex.trim().match(/^#([0-9a-f]{6})$/i);
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** 色相だけを deg 度回す（HSL で回して戻す）。アクセント色から、少し暖かい色・少し冷たい色を作る。 */
export function rotateHue([r, g, b]: Rgb, deg: number): Rgb {
  if (deg === 0) return [r, g, b];
  const [rn, gn, bn] = [r / 255, g / 255, b / 255];
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const l = (max + min) / 2;
  const d = max - min;
  const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
  let h = 0;
  if (d !== 0) {
    if (max === rn) h = ((gn - bn) / d) % 6;
    else if (max === gn) h = (bn - rn) / d + 2;
    else h = (rn - gn) / d + 4;
  }
  h = (((h * 60 + deg) % 360) + 360) % 360;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  const [r1, g1, b1] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  return [Math.round((r1 + m) * 255), Math.round((g1 + m) * 255), Math.round((b1 + m) * 255)];
}

export interface Blob {
  /** 中心（幅・高さに対する割合） */
  x: number;
  y: number;
  /** 半径（幅に対する割合） */
  r: number;
  /** 色相をアクセントから何度ずらすか */
  hue: number;
  alpha: number;
}

/**
 * t 秒時点の光の位置。3 つの光が、画面の上のほうをそれぞれ違う周期でゆっくり漂う。
 * 周期が互いに割り切れないので、同じ形にはなかなか戻らない。
 */
export function blobsAt(t: number): Blob[] {
  return [
    { x: 0.5 + 0.16 * Math.sin(t / 19), y: 0.04 + 0.05 * Math.cos(t / 23), r: 0.42, hue: 0, alpha: 0.5 },
    { x: 0.3 + 0.12 * Math.cos(t / 29), y: 0.14 + 0.07 * Math.sin(t / 17), r: 0.3, hue: 26, alpha: 0.34 },
    { x: 0.72 + 0.11 * Math.sin(t / 31 + 1.3), y: 0.1 + 0.06 * Math.cos(t / 21 + 0.7), r: 0.28, hue: -22, alpha: 0.3 },
  ];
}

/** カードの上でのポインタの位置（0〜1）→ 傾きの角度。最大 maxDeg 度。tvOS のポスターと同じ向き（ポインタの側が手前に浮く）。 */
export function tiltFor(px: number, py: number, maxDeg = 4): { rx: number; ry: number } {
  const cx = Math.min(1, Math.max(0, px)) - 0.5;
  const cy = Math.min(1, Math.max(0, py)) - 0.5;
  // +0 に丸めて、中央で -0 を返さない
  return { rx: -cy * 2 * maxDeg + 0, ry: cx * 2 * maxDeg + 0 };
}
