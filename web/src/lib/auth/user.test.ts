import { describe, expect, it } from "vitest";
import { describeAgent, initialsOf, toAppUser } from "@/lib/auth/user";

describe("toAppUser", () => {
  it("セッションの利用者を画面用に写す", () => {
    const u = toAppUser({ name: "山田 太郎", email: "t@example.com", emailVerified: true, createdAt: new Date("2026-01-02") });
    expect(u).toMatchObject({ name: "山田 太郎", firstName: "山田", initials: "山", email: "t@example.com" });
    expect(u.emailVerifiedAt).not.toBeNull();
    expect(toAppUser({ name: "", email: "x@y.z", emailVerified: false }).emailVerifiedAt).toBeNull();
  });

  it("頭文字: 日本語は 1 文字、英語は 2 語の頭", () => {
    expect(initialsOf("佐藤花子", "a@b")).toBe("佐");
    expect(initialsOf("Jane Doe", "a@b")).toBe("JD");
    expect(initialsOf("", "kate@b.c")).toBe("K");
  });
});

describe("describeAgent", () => {
  it("User-Agent をブラウザと OS の短い名前にする", () => {
    expect(describeAgent("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36")).toBe("Chrome · macOS");
    expect(describeAgent("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1")).toBe("Safari · iOS");
    expect(describeAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edg/140.0")).toBe("Edge · Windows");
    expect(describeAgent(null)).toBe("不明な端末");
  });
});
