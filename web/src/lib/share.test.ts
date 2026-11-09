import { describe, expect, it } from "vitest";
import { shareUrl } from "@/lib/share";

describe("shareUrl", () => {
  it("公開範囲が private かトークンが無ければリンクを出さない", () => {
    expect(shareUrl("https://a.test", "private", "tok")).toBeNull();
    expect(shareUrl("https://a.test", "org", null)).toBeNull();
  });
  it("org・public は /s/<token>", () => {
    expect(shareUrl("https://a.test/", "org", "Ab_-9")).toBe("https://a.test/s/Ab_-9");
    expect(shareUrl("https://a.test", "public", "x")).toBe("https://a.test/s/x");
  });
});
