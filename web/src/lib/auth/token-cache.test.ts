import { describe, expect, it } from "vitest";
import { TokenCache, jwtExp } from "@/lib/auth/token-cache";

const b64 = (o: object) => Buffer.from(JSON.stringify(o)).toString("base64url");
const tok = (exp: number) => `${b64({ alg: "EdDSA" })}.${b64({ sub: "u", exp })}.sig`;

describe("jwtExp", () => {
  it("exp（秒）を読み、読めなければ null", () => {
    expect(jwtExp(tok(1700000000))).toBe(1700000000);
    expect(jwtExp("garbage")).toBeNull();
    expect(jwtExp(`${b64({})}.${b64({ sub: "u" })}.s`)).toBeNull();
  });
});

describe("TokenCache", () => {
  it("期限の 60 秒前までは同じ JWT を返し、その後は取り直す", async () => {
    let now = 1_000_000;
    let minted = 0;
    const cache = new TokenCache({ now: () => now });
    const mint = async () => tok(now / 1000 + 900 + minted++ * 0);
    const a = await cache.get("s1", mint);
    expect(await cache.get("s1", mint)).toBe(a);
    expect(minted).toBe(1);
    now += (900 - 59) * 1000;
    await cache.get("s1", mint);
    expect(minted).toBe(2);
  });

  it("同じセッションの同時要求は 1 回だけ発行する", async () => {
    let minted = 0;
    const cache = new TokenCache({ now: () => 0 });
    const mint = async () => {
      minted++;
      await new Promise((r) => setTimeout(r, 5));
      return tok(900);
    };
    await Promise.all([cache.get("s", mint), cache.get("s", mint), cache.get("s", mint)]);
    expect(minted).toBe(1);
  });

  it("上限を超えたら古いものから捨てる。発行に失敗したら覚えない", async () => {
    const cache = new TokenCache({ now: () => 0, max: 2 });
    await cache.get("a", async () => tok(900));
    await cache.get("b", async () => tok(900));
    await cache.get("c", async () => tok(900));
    expect(cache.size).toBe(2);
    await expect(cache.get("x", async () => Promise.reject(new Error("no")))).rejects.toThrow();
    expect(cache.size).toBe(2);
  });

  it("forget でセッションの JWT を捨てる", async () => {
    let minted = 0;
    const cache = new TokenCache({ now: () => 0 });
    const mint = async () => (minted++, tok(900));
    await cache.get("s", mint);
    cache.forget("s");
    await cache.get("s", mint);
    expect(minted).toBe(2);
  });
});
