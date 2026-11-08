import { describe, it, expect } from "vitest";
import { getDictionary } from "./dictionary";
import { ja } from "./locales/ja";

describe("dictionary", () => {
  it("日本語の辞書を返す", () => {
    expect(getDictionary()).toBe(ja);
  });
  it("common に基本の操作文言がある", () => {
    expect(ja.common.cancel).toBe("キャンセル");
  });
});
