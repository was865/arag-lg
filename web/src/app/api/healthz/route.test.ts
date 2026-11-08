import { describe, expect, it, vi } from "vitest";

vi.mock("next/server", () => ({ connection: vi.fn(async () => undefined) }));

import { GET } from "./route";

describe("GET /api/healthz", () => {
  it("200 と status=ok を返す", async () => {
    const res = await GET();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ status: "ok" });
  });
});
