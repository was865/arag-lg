import { describe, expect, it } from "vitest";
import { authRedirect, safeNext } from "@/lib/auth/guard";

describe("authRedirect", () => {
  it("未ログインでアプリの画面を開くと /login?next= へ", () => {
    expect(authRedirect("/c/t1", "?x=1", false)).toBe("/login?next=%2Fc%2Ft1%3Fx%3D1");
    expect(authRedirect("/", "", false)).toBe("/login");
  });

  it("ログイン画面・再設定画面は未ログインでも開ける", () => {
    expect(authRedirect("/login", "", false)).toBeNull();
    expect(authRedirect("/reset-password", "?token=a", false)).toBeNull();
    expect(authRedirect("/s/abc", "", false)).toBeNull();
    expect(authRedirect("/s/abc", "", true)).toBeNull();
  });

  it("ログイン済みで /login を開くとアプリ（next があればそこ）へ", () => {
    expect(authRedirect("/login", "", true)).toBe("/");
    expect(authRedirect("/login", "?next=%2Flibrary", true)).toBe("/library");
    expect(authRedirect("/library", "", true)).toBeNull();
  });
});

describe("safeNext", () => {
  it("自サイト内のパスだけ受け付ける（オープンリダイレクト対策）", () => {
    expect(safeNext("/c/1")).toBe("/c/1");
    expect(safeNext("//evil.example")).toBe("/");
    expect(safeNext("https://evil.example")).toBe("/");
    expect(safeNext("/\\evil")).toBe("/");
    expect(safeNext(null)).toBe("/");
  });
});
