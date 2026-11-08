import { describe, expect, it, vi } from "vitest";
import { proxy, upstreamUrl } from "./proxy";

const opts = (fetchImpl: typeof fetch) => ({ baseUrl: "http://api:8000/", devUserId: "u1", devRole: "member", fetchImpl });

describe("proxy", () => {
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
});
