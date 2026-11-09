import { describe, expect, it } from "vitest";
import { GUIDE_STEPS, guideKey, shouldShowGuide } from "./onboarding";

describe("初回ガイド", () => {
  it("利用者ごとに記録する", () => {
    expect(guideKey("u1")).not.toBe(guideKey("u2"));
  });

  it("利用者が分かり、まだ見ていないときだけ出す", () => {
    expect(shouldShowGuide({ userId: "u1", seen: null })).toBe(true);
    expect(shouldShowGuide({ userId: "u1", seen: "1" })).toBe(false);
    expect(shouldShowGuide({ userId: null, seen: null })).toBe(false);
  });

  it("4 ステップ", () => {
    expect(GUIDE_STEPS).toHaveLength(4);
  });
});
