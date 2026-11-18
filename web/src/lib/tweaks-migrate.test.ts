import { describe, expect, it } from "vitest";
import { DEFAULT_ACCENT } from "@/lib/constants";
import { TWEAKS_VERSION, migrateStoredTweaks } from "@/lib/tweaks-migrate";

describe("migrateStoredTweaks（保存済みの表示設定の移行）", () => {
  it("旧版の既定だった橙は、新しい既定の朱に替える", () => {
    expect(migrateStoredTweaks({ dark: true, accent: "#D97757" })).toEqual({ dark: true, accent: DEFAULT_ACCENT, v: TWEAKS_VERSION });
    expect(migrateStoredTweaks({ accent: "#d97757" }).accent).toBe(DEFAULT_ACCENT);
  });
  it("自分で選んだ今の色は残す", () => {
    expect(migrateStoredTweaks({ accent: "#4A76AE" }).accent).toBe("#4A76AE");
    expect(migrateStoredTweaks({ accent: "#438067", v: TWEAKS_VERSION }).accent).toBe("#438067");
  });
  it("選べなくなった色は、版に関わらず近い色へ移す（R48）", () => {
    expect(migrateStoredTweaks({ accent: "#D97757", v: TWEAKS_VERSION }).accent).toBe("#D2402B");
    expect(migrateStoredTweaks({ accent: "#3FA77E", v: TWEAKS_VERSION }).accent).toBe("#438067");
    expect(migrateStoredTweaks({ accent: "#3d7ee6" }).accent).toBe("#4A76AE");
    expect(migrateStoredTweaks({ accent: "#8B6FE0", v: TWEAKS_VERSION }).accent).toBe("#4A76AE");
  });
});
