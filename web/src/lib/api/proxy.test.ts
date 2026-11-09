import { describe, expect, it, vi } from "vitest";
import { proxy, upstreamUrl } from "./proxy";

const opts = (fetchImpl: typeof fetch) => ({ baseUrl: "http://api:8000/", devUserId: "u1", devRole: "member", fetchImpl });

describe("proxy", () => {
  it("監査ログへの書き込みはブラウザから通さない（読み取りは通す）", async () => {
    const fetchImpl = vi.fn(async () => new Response("{}"));
    const post = new Request("http://web/api/v1/admin/audit", { method: "POST", body: "{}" });
    expect((await proxy(post, ["admin", "audit"], opts(fetchImpl as unknown as typeof fetch))).status).toBe(403);
    expect((await proxy(post.clone(), ["Admin", "audit", ""], opts(fetchImpl as unknown as typeof fetch))).status).toBe(403);
    expect(fetchImpl).not.toHaveBeenCalled();
    const get = new Request("http://web/api/v1/admin/audit?action=member.");
    expect((await proxy(get, ["admin", "audit"], opts(fetchImpl as unknown as typeof fetch))).status).toBe(200);
  });

  it("パスとクエリを上流の /v1 に写す", () => {
    expect(upstreamUrl("http://api:8000/", ["threads", "a b"], "?limit=5")).toBe("http://api:8000/v1/threads/a%20b?limit=5");
  });

  it("必要なヘッダだけ渡し、開発用の利用者ヘッダを付ける", async () => {
    const fetchImpl = vi.fn(async () => new Response("{}", { headers: { "content-type": "application/json", "set-cookie": "x=1" } }));
    const req = new Request("http://web/api/v1/runs/r1/stream", {
      headers: { "last-event-id": "1-0", cookie: "secret=1", accept: "text/event-stream" },
    });
    const res = await proxy(req, ["runs", "r1", "stream"], opts(fetchImpl as unknown as typeof fetch));
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    const h = new Headers(init.headers);
    expect(url).toBe("http://api:8000/v1/runs/r1/stream");
    expect(h.get("last-event-id")).toBe("1-0");
    expect(h.get("x-dev-user-id")).toBe("u1");
    expect(h.get("cookie")).toBeNull();
    expect(init.signal).toBe(req.signal);
    expect(res.headers.get("set-cookie")).toBeNull();
    expect(res.headers.get("content-type")).toBe("application/json");
  });

  it("本文をバッファせずに流す", async () => {
    let push: (s: string) => void = () => {};
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        push = (s) => c.enqueue(new TextEncoder().encode(s));
      },
    });
    const fetchImpl = vi.fn(async () => new Response(body, { headers: { "content-type": "text/event-stream" } }));
    const res = await proxy(new Request("http://web/api/v1/x"), ["x"], opts(fetchImpl as unknown as typeof fetch));
    const reader = res.body!.getReader();
    push("event: a\n\n");
    const first = await reader.read();
    expect(new TextDecoder().decode(first.value)).toBe("event: a\n\n");
    await reader.cancel();
  });

  it("POST の本文と状態コードを渡す", async () => {
    const fetchImpl = vi.fn(async (_u: string, init: RequestInit) => {
      const text = await new Response(init.body).text();
      return Response.json({ got: text }, { status: 202 });
    });
    const req = new Request("http://web/api/v1/runs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query: "q" }),
    });
    const res = await proxy(req, ["runs"], opts(fetchImpl as unknown as typeof fetch));
    expect(res.status).toBe(202);
    expect(await res.json()).toEqual({ got: '{"query":"q"}' });
  });

  it("上流に繋がらなければ 502 と日本語の説明", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("fetch failed");
    });
    const res = await proxy(new Request("http://web/api/v1/x"), ["x"], opts(fetchImpl as unknown as typeof fetch));
    expect(res.status).toBe(502);
    expect((await res.json()).error.code).toBe("upstream_unavailable");
  });

  it("authorize の見出しを付けて送り、利用者ヘッダは付けない", async () => {
    const fetchImpl = vi.fn(async () => new Response("{}"));
    await proxy(new Request("http://web/api/v1/kbs"), ["kbs"], {
      baseUrl: "http://api:8000",
      fetchImpl: fetchImpl as unknown as typeof fetch,
      authorize: async () => new Headers({ authorization: "Bearer t" }),
    });
    const h = new Headers((fetchImpl.mock.calls[0] as unknown as [string, RequestInit])[1].headers);
    expect(h.get("authorization")).toBe("Bearer t");
    expect(h.get("x-dev-user-id")).toBeNull();
  });

  it("authorize が応答を返したら上流を呼ばずにそれを返す（未ログインの 401）", async () => {
    const fetchImpl = vi.fn(async () => new Response("{}"));
    const res = await proxy(new Request("http://web/api/v1/kbs"), ["kbs"], {
      baseUrl: "http://api:8000",
      fetchImpl: fetchImpl as unknown as typeof fetch,
      authorize: async () => Response.json({ error: { code: "unauthenticated" } }, { status: 401 }),
    });
    expect(res.status).toBe(401);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("状態を変える要求は Origin が許可外なら 403（GET と Origin 無しは通す）", async () => {
    const fetchImpl = vi.fn(async () => new Response("{}"));
    const o = { ...opts(fetchImpl as unknown as typeof fetch), allowedOrigins: ["http://localhost:3100"] };
    const post = (origin?: string) =>
      new Request("http://web/api/v1/runs", {
        method: "POST",
        body: "{}",
        headers: origin ? { origin } : {},
      });
    expect((await proxy(post("http://evil.example"), ["runs"], o)).status).toBe(403);
    expect((await proxy(post("http://localhost:3100"), ["runs"], o)).status).toBe(200);
    expect((await proxy(post(), ["runs"], o)).status).toBe(200);
    const get = new Request("http://web/api/v1/kbs", { headers: { origin: "http://evil.example" } });
    expect((await proxy(get, ["kbs"], o)).status).toBe(200);
    expect(fetchImpl).toHaveBeenCalledTimes(3);
  });
});
