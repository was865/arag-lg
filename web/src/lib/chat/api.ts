/** ブラウザから Next の中継（/api/v1）経由で対話 API を呼ぶ。型は OpenAPI から生成したもの。 */
import createClient from "openapi-fetch";
import type { components, paths } from "@/lib/api/schema";
import type { FeedbackReasonTag } from "@/lib/feedback-types";

type S = components["schemas"];
export type ThreadOut = S["ThreadOut"];
export type ThreadDetail = S["ThreadDetail"];
export type ModelOut = S["ModelOut"];
export type RunCreated = S["RunCreated"];
export type ActiveRunOut = S["ActiveRunOut"];
export type ThreadSearchHit = S["ThreadSearchHit"];
export type RefreshOut = S["RefreshOut"];
export type SystemStatus = S["SystemStatus"];
export type McpStatsOut = S["McpStatsOut"];

/** API のエラー（`{error: {code, message}}`）。message は日本語。 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

const client = createClient<paths>({ baseUrl: "/api" });

function fail(status: number, error: unknown): never {
  const e = (error as { error?: { code?: string; message?: string } } | undefined)?.error;
  throw new ApiError(status, e?.code ?? "unknown", e?.message ?? "通信に失敗しました。時間をおいてお試しください");
}

export type StartRunBody = S["RunRequest"];

export const chatApi = {
  async models() {
    const { data, error, response } = await client.GET("/v1/models");
    if (!data) fail(response.status, error);
    return data;
  },
  async threads() {
    const { data, error, response } = await client.GET("/v1/threads", { params: { query: { limit: 200 } } });
    if (!data) fail(response.status, error);
    return data.items;
  },
  /** 題名・質問・回答の本文でスレッドを探す（空白区切りの語はすべて含む）。 */
  async searchThreads(q: string, signal?: AbortSignal): Promise<ThreadSearchHit[]> {
    const { data, error, response } = await client.GET("/v1/threads/search", {
      params: { query: { q, limit: 30 } },
      signal,
    });
    if (!data) fail(response.status, error);
    return data.items;
  },
  async thread(id: string) {
    const { data, error, response } = await client.GET("/v1/threads/{thread_id}", {
      params: { path: { thread_id: id } },
    });
    if (!data) fail(response.status, error);
    return data;
  },
  async patchThread(id: string, body: { title?: string; pinned?: boolean; visibility?: "private" | "org" | "public" }) {
    const { data, error, response } = await client.PATCH("/v1/threads/{thread_id}", {
      params: { path: { thread_id: id } },
      body,
    });
    if (!data) fail(response.status, error);
    return data;
  },
  async deleteThread(id: string) {
    const { error, response } = await client.DELETE("/v1/threads/{thread_id}", {
      params: { path: { thread_id: id } },
    });
    if (!response.ok) fail(response.status, error);
  },
  /** threadId が無ければ新しいスレッドを作って質問する。 */
  async startRun(threadId: string | null, body: StartRunBody): Promise<RunCreated> {
    const res = threadId
      ? await client.POST("/v1/threads/{thread_id}/runs", { params: { path: { thread_id: threadId } }, body })
      : await client.POST("/v1/runs", { body });
    if (!res.data) fail(res.response.status, res.error);
    return res.data;
  },
  async cancelRun(runId: string) {
    const { error, response } = await client.POST("/v1/runs/{run_id}/cancel", {
      params: { path: { run_id: runId } },
    });
    if (!response.ok) fail(response.status, error);
  },
  async feedback(messageId: string, body: { rating: "up" | "down"; reason_tags?: FeedbackReasonTag[]; comment?: string | null }) {
    const { data, error, response } = await client.PUT("/v1/messages/{message_id}/feedback", {
      params: { path: { message_id: messageId } },
      body: { reason_tags: [], ...body },
    });
    if (!data) fail(response.status, error);
    return data;
  },
  /** 出典の社内システムの記録を呼び直す（specs/033 R17）。 */
  async refreshRecord(messageId: string, sectionId: string) {
    const { data, error, response } = await client.POST("/v1/messages/{message_id}/records/{section_id}/refresh", {
      params: { path: { message_id: messageId, section_id: sectionId } },
    });
    if (!data) fail(response.status, error);
    return data;
  },
  /** 使える社内システムと接続の状態（specs/033 R19）。 */
  async systemsStatus() {
    const { data, error, response } = await client.GET("/v1/systems/status");
    if (!data) fail(response.status, error);
    return data.systems;
  },
  /** 社内システムの直近の呼び出しの数字（管理者、specs/033 R21）。 */
  async mcpStats(serverId: string) {
    const { data, error, response } = await client.GET("/v1/admin/mcp-servers/{server_id}/stats", {
      params: { path: { server_id: serverId } },
    });
    if (!data) fail(response.status, error);
    return data;
  },
  async documentStats(): Promise<{ documents?: number; by_status?: Record<string, number> }> {
    const res = await fetch("/api/v1/documents/stats", { cache: "no-store" });
    return res.ok ? res.json() : {};
  },
};

export function streamUrl(runId: string): string {
  return `/api/v1/runs/${encodeURIComponent(runId)}/stream`;
}
