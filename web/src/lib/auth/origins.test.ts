import { describe, expect, it } from "vitest";
import { siteOrigins } from "@/lib/auth/origins";

describe("siteOrigins", () => {
  it("BETTER_AUTH_URL だけなら、その 1 つ（末尾の / は落とす）", () => {
    expect(siteOrigins("http://localhost:3100/", undefined)).toEqual(["http://localhost:3100"]);
  });

  it("ARAG_EXTRA_ORIGINS をカンマ区切りで足す（空白・空要素・重複・パスは落とす）", () => {
    expect(
      siteOrigins("http://localhost:3100", " https://mac.tail.ts.net/ , ,http://100.1.2.3:3100/x, http://localhost:3100"),
    ).toEqual(["http://localhost:3100", "https://mac.tail.ts.net", "http://100.1.2.3:3100"]);
  });

  it("URL として読めないものは無視する", () => {
    expect(siteOrigins("http://localhost:3100", "mac.tail.ts.net,ftp://x")).toEqual(["http://localhost:3100"]);
  });
});
