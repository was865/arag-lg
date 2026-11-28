"use client";

/** 社内システム（MCP）の管理の一覧を読む（specs/032・038）。reload で読み直す。 */
import createClient from "openapi-fetch";
import { useCallback, useEffect, useState } from "react";
import type { components, paths } from "@/lib/api/schema";

export type McpOverview = components["schemas"]["McpAdminOut"];
export const mcpClient = createClient<paths>({ baseUrl: "/api" });

export function apiErrorMessage(e: unknown, fallback: string): string {
  const m = (e as { error?: { message?: string } } | undefined)?.error?.message;
  return m ?? fallback;
}

export function useMcpAdmin(): { data: McpOverview | null; error: string | null; reload: () => void } {
  const [data, setData] = useState<McpOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [n, setN] = useState(0);
  useEffect(() => {
    let alive = true;
    void mcpClient.GET("/v1/admin/mcp-servers").then(({ data: d, error: e }) => {
      if (!alive) return;
      if (d) {
        setData(d);
        setError(null);
      } else setError(apiErrorMessage(e, "一覧を読み込めませんでした"));
    });
    return () => {
      alive = false;
    };
  }, [n]);
  const reload = useCallback(() => setN((x) => x + 1), []);
  return { data, error, reload };
}
