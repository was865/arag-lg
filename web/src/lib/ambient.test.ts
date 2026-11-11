import { describe, expect, it } from "vitest";
import { blobsAt, hexToRgb, rotateHue, tiltFor } from "@/lib/ambient";

describe("色の計算（首ページの光）", () => {
  it("16 進の色を RGB にする。読めない値は null", () => {
    expect(hexToRgb("#D2402B")).toEqual([210, 64, 43]);
    expect(hexToRgb(" #3fa77e ")).toEqual([63, 167, 126]);
    expect(hexToRgb("red")).toBeNull();
  });
  it("色相を回しても明るさはほぼ変わらず、0 度なら元の色", () => {
    expect(rotateHue([210, 64, 43], 0)).toEqual([210, 64, 43]);
    const warm = rotateHue([210, 64, 43], 28);
    expect(warm).not.toEqual([210, 64, 43]);
    expect(Math.max(...warm)).toBeGreaterThan(180);
  });
});

describe("blobsAt（ゆっくり漂う光の位置）", () => {
  it("光は 3 つで、いつも画面の上半分の中にある（下の文字の邪魔をしない）", () => {
    for (const t of [0, 3.7, 41, 999]) {
      const blobs = blobsAt(t);
      expect(blobs).toHaveLength(3);
      for (const b of blobs) {
        expect(b.x).toBeGreaterThan(0.05);
        expect(b.x).toBeLessThan(0.95);
        expect(b.y).toBeLessThan(0.5);
        expect(b.r).toBeGreaterThan(0.2);
      }
    }
  });
  it("時間が進むと位置が変わるが、1 秒での動きはわずか", () => {
    const a = blobsAt(10)[0];
    const b = blobsAt(11)[0];
    expect(a.x).not.toBe(b.x);
    expect(Math.abs(a.x - b.x)).toBeLessThan(0.05);
  });
});

describe("tiltFor（カードの傾き）", () => {
  it("中央では傾かず、端でも最大角を超えない", () => {
    expect(tiltFor(0.5, 0.5)).toEqual({ rx: 0, ry: 0 });
    const corner = tiltFor(1, 0);
    expect(corner.ry).toBeCloseTo(4);
    expect(corner.rx).toBeCloseTo(4);
    expect(tiltFor(2, -3).ry).toBeLessThanOrEqual(4);
  });
  it("右へ寄せると右が奥へ、下へ寄せると下が奥へ倒れる向き", () => {
    expect(tiltFor(0.9, 0.5).ry).toBeGreaterThan(0);
    expect(tiltFor(0.5, 0.9).rx).toBeLessThan(0);
  });
});
