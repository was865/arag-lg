import { describe, expect, it } from "vitest";
import { DEFAULT_ACCENT } from "@/lib/constants";
import { TWEAKS_VERSION, migrateStoredTweaks } from "@/lib/tweaks-migrate";

describe("migrateStoredTweaks（保存済みの表示設定の移行）", () => {
  it("旧版の既定だった橙は、新しい既定の朱に替える", () => {
    expect(migrateStoredTweaks({ dark: true, accent: "#D97757" })).toEqual({ dark: true, accent: DEFAULT_ACCENT, v: TWEAKS_VERSION });
    expect(migrateStoredTweaks({ accent: "#d97757" }).accent).toBe(DEFAULT_ACCENT);
  });
  it("自分で選んだほかの色は残す", () => {
    expect(migrateStoredTweaks({ accent: "#3FA77E" }).accent).toBe("#3FA77E");
  });
  it("移行済み（v あり）なら、橙を選び直していても触らない", () => {
    expect(migrateStoredTweaks({ accent: "#D97757", v: TWEAKS_VERSION }).accent).toBe("#D97757");
  });
});
