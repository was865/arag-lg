import "server-only";
import createClient from "openapi-fetch";
import type { paths } from "./schema";

/** Python API の型付きクライアント（サーバ側専用）。型は api/openapi.json から生成する。 */
export function apiClient(
  baseUrl: string = process.env.API_BASE_URL ?? "http://localhost:8100",
  fetchImpl?: typeof fetch,
) {
  return createClient<paths>({ baseUrl, ...(fetchImpl ? { fetch: fetchImpl } : {}) });
}
