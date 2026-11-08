import { describe, expect, it, vi } from "vitest";
import { apiClient } from "./client";

describe("apiClient", () => {
  it("baseUrl に対して型付きパスで GET する", async () => {
    const fetchMock = vi.fn(async (req: Request) => {
      expect(req.url).toBe("http://api.test/healthz");
      return Response.json({ status: "ok" });
    });
    const { data } = await apiClient("http://api.test", fetchMock as unknown as typeof fetch).GET("/healthz");
    expect(data).toEqual({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("503 の readiness はエラーとして受け取れる", async () => {
    const body = { status: "unavailable", checks: { postgres: "fail" } };
    const fetchMock = vi.fn(async () => Response.json(body, { status: 503 }));
    const { data, error, response } = await apiClient("http://api.test", fetchMock as unknown as typeof fetch).GET(
      "/readyz",
    );
    expect(response.status).toBe(503);
    expect(data).toBeUndefined();
    expect(error).toEqual(body);
  });
});
