import { describe, expect, it } from "vitest";
import { guideKey, isVisibleRect, placePopover, shouldShowGuide, spotlightRect, TOUR_STEPS } from "./onboarding";

describe("初回ガイドの表示", () => {
  it("利用者ごとに記録する", () => {
    expect(guideKey("u1")).not.toBe(guideKey("u2"));
  });

  it("利用者が分かり、まだ見ていないときだけ出す", () => {
    expect(shouldShowGuide({ userId: "u1", seen: null })).toBe(true);
    expect(shouldShowGuide({ userId: "u1", seen: "1" })).toBe(false);
    expect(shouldShowGuide({ userId: null, seen: null })).toBe(false);
  });

  it("4 ステップで id は重複しない", () => {
    expect(new Set(TOUR_STEPS.map((s) => s.id)).size).toBe(4);
  });
});

describe("isVisibleRect", () => {
  const vp = { width: 375, height: 812 };
  it("画面内の対象は見えている", () => {
    expect(isVisibleRect({ left: 10, top: 700, width: 300, height: 60 }, vp)).toBe(true);
  });
  it("幅 0・画面外（閉じたサイドバー）・無しは見えていない", () => {
    expect(isVisibleRect({ left: 10, top: 10, width: 0, height: 20 }, vp)).toBe(false);
    expect(isVisibleRect({ left: -280, top: 100, width: 260, height: 80 }, vp)).toBe(false);
    expect(isVisibleRect(null, vp)).toBe(false);
  });
});

describe("spotlightRect", () => {
  it("対象に 8px のパディングを付ける", () => {
    expect(spotlightRect({ left: 100, top: 200, width: 50, height: 30 })).toEqual({
      left: 92,
      top: 192,
      width: 66,
      height: 46,
    });
  });

  it("負座標は 0 に丸め、反対側の端は保つ", () => {
    const r = spotlightRect({ left: 4, top: 2, width: 50, height: 30 });
    expect([r.left, r.top]).toEqual([0, 0]);
    expect(r.left + r.width).toBe(62);
    expect(r.top + r.height).toBe(40);
  });
});

describe("placePopover", () => {
  const viewport = { width: 1200, height: 800 };
  const popover = { width: 320, height: 140 };

  it("下に空きがあれば下、無ければ上に出す", () => {
    expect(placePopover({ left: 100, top: 100, width: 200, height: 60 }, popover, viewport)).toMatchObject({
      side: "bottom",
      top: 172,
    });
    expect(placePopover({ left: 100, top: 700, width: 200, height: 60 }, popover, viewport)).toMatchObject({
      side: "top",
      top: 548,
    });
  });

  it("左右は画面の 16px 内側に収める", () => {
    expect(placePopover({ left: 0, top: 100, width: 40, height: 40 }, popover, viewport).left).toBe(16);
    expect(placePopover({ left: 1150, top: 100, width: 40, height: 40 }, popover, viewport).left).toBe(864);
  });

  it("対象がほぼ全画面でもはみ出さない", () => {
    const p = placePopover({ left: 0, top: 0, width: 1200, height: 800 }, popover, viewport);
    expect(p.top).toBeGreaterThanOrEqual(16);
    expect(p.top + popover.height).toBeLessThanOrEqual(784);
  });
});
