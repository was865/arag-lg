/** 文書ライブラリの API（中継 /api/v1 経由）。型は OpenAPI から生成したもの。 */
import createClient from "openapi-fetch";
import type { components, paths } from "@/lib/api/schema";
import { ApiError } from "@/lib/chat/api";

type S = components["schemas"];
export type DocumentOut = S["DocumentOut"];
export type TrashItem = S["TrashItem"];
export type UploadResult = S["UploadResult"];
export type FolderOut = S["FolderOut"];
export type OutlineSection = S["OutlineSection"];
export type SectionOut = S["SectionOut"];

const client = createClient<paths>({ baseUrl: "/api" });

function fail(status: number, error: unknown): never {
  const e = (error as { error?: { code?: string; message?: string } } | undefined)?.error;
  throw new ApiError(status, e?.code ?? "unknown", e?.message ?? "通信に失敗しました。時間をおいてお試しください");
}

export interface DocumentQuery {
  kbId: string | null;
  /** フォルダの中だけ。null ならルート直下だけ（root_only）、undefined なら KB 全体。 */
  folderId?: string | null;
  status?: string | null;
  /** ファイル名の部分一致。 */
  q?: string | null;
  cursor?: string | null;
  limit?: number;
}

export const libraryApi = {
  async documents(q: DocumentQuery) {
    const { data, error, response } = await client.GET("/v1/documents", {
      params: {
        query: {
          kb_id: q.kbId ?? undefined,
          folder_id: q.folderId ?? undefined,
          root_only: q.folderId === null ? true : undefined,
          status: q.status ?? undefined,
          q: q.q || undefined,
          cursor: q.cursor ?? undefined,
          limit: q.limit ?? 50,
        },
      },
    });
    if (!data) fail(response.status, error);
    return data;
  },
  async stats(kbId: string | null) {
    const { data, error, response } = await client.GET("/v1/documents/stats", {
      params: { query: { kb_id: kbId ?? undefined } },
    });
    if (!data) fail(response.status, error);
    return data;
  },
  async rename(id: string, filename: string) {
    const { data, error, response } = await client.PATCH("/v1/documents/{doc_id}", {
      params: { path: { doc_id: id } },
      body: { filename },
    });
    if (!data) fail(response.status, error);
    return data;
  },
  async remove(id: string) {
    const { error, response } = await client.DELETE("/v1/documents/{doc_id}", { params: { path: { doc_id: id } } });
    if (!response.ok) fail(response.status, error);
  },
  async restore(item: Pick<TrashItem, "kind" | "id">) {
    const res =
      item.kind === "document"
        ? await client.POST("/v1/documents/{doc_id}/restore", { params: { path: { doc_id: item.id } } })
        : item.kind === "folder"
          ? await client.POST("/v1/folders/{folder_id}/restore", { params: { path: { folder_id: item.id } } })
          : await client.POST("/v1/kbs/{kb_id}/restore", { params: { path: { kb_id: item.id } } });
    if (!res.response.ok) fail(res.response.status, res.error);
  },
  async purge(id: string) {
    const { error, response } = await client.DELETE("/v1/documents/{doc_id}/purge", {
      params: { path: { doc_id: id } },
    });
    if (!response.ok) fail(response.status, error);
  },
  async trash() {
    const { data, error, response } = await client.GET("/v1/trash");
    if (!data) fail(response.status, error);
    return data;
  },
  async folders(kbId: string) {
    const { data, error, response } = await client.GET("/v1/kbs/{kb_id}/folders", {
      params: { path: { kb_id: kbId } },
    });
    if (!data) fail(response.status, error);
    return data;
  },
  async createFolder(kbId: string, name: string, parentId: string | null) {
    const { data, error, response } = await client.POST("/v1/kbs/{kb_id}/folders", {
      params: { path: { kb_id: kbId } },
      body: { name, parent_id: parentId },
    });
    if (!data) fail(response.status, error);
    return data;
  },
  async renameFolder(id: string, name: string) {
    const { data, error, response } = await client.PATCH("/v1/folders/{folder_id}", {
      params: { path: { folder_id: id } },
      body: { name },
    });
    if (!data) fail(response.status, error);
    return data;
  },
  async removeFolder(id: string) {
    const { error, response } = await client.DELETE("/v1/folders/{folder_id}", {
      params: { path: { folder_id: id } },
    });
    if (!response.ok) fail(response.status, error);
  },
  /** 文書をフォルダへ移す（folderId = null ならルート直下）。 */
  async moveDocuments(ids: string[], folderId: string | null) {
    const { data, error, response } = await client.POST("/v1/documents/bulk-move", {
      body: { ids, folder_id: folderId },
    });
    if (!data) fail(response.status, error);
    return data;
  },
  async document(id: string) {
    const { data, error, response } = await client.GET("/v1/documents/{doc_id}", { params: { path: { doc_id: id } } });
    if (!data) fail(response.status, error);
    return data;
  },
  async outline(id: string) {
    const { data, error, response } = await client.GET("/v1/documents/{doc_id}/outline", {
      params: { path: { doc_id: id } },
    });
    if (!data) fail(response.status, error);
    return data;
  },
  /** 章を本文つきで順に（R4: 50 件ずつ）。 */
  async sections(id: string, offset: number, limit = 50) {
    const { data, error, response } = await client.GET("/v1/documents/{doc_id}/sections", {
      params: { path: { doc_id: id }, query: { offset, limit } },
    });
    if (!data) fail(response.status, error);
    return data;
  },
  /** まとめてごみ箱へ（1 回 500 件まで。1 件でも書けなければ全体が失敗する）。 */
  async removeDocuments(ids: string[]) {
    const { data, error, response } = await client.POST("/v1/documents/bulk-delete", { body: { ids } });
    if (!data) fail(response.status, error);
    return data;
  },
  async retryJob(jobId: string) {
    const { error, response } = await client.POST("/v1/jobs/{job_id}/retry", { params: { path: { job_id: jobId } } });
    if (!response.ok) fail(response.status, error);
  },
};

/** 1 ファイルを送る。fetch では送信の進み具合が取れないので XHR を使う。 */
export function uploadFile(
  kbId: string,
  file: File,
  onProgress: (ratio: number) => void,
  signal?: AbortSignal,
  folderId?: string | null,
): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/v1/kbs/${encodeURIComponent(kbId)}/uploads`);
    xhr.responseType = "json";
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response as UploadResult);
      else {
        const e = (xhr.response as { error?: { code?: string; message?: string } } | null)?.error;
        reject(new ApiError(xhr.status, e?.code ?? "upload_failed", e?.message ?? "アップロードに失敗しました"));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "network", "通信に失敗しました"));
    xhr.onabort = () => reject(new ApiError(0, "aborted", "アップロードを取り消しました"));
    signal?.addEventListener("abort", () => xhr.abort());
    const form = new FormData();
    form.append("files", file, file.name);
    if (folderId) form.append("folder_id", folderId);
    xhr.send(form);
  });
}

export function originalUrl(id: string): string {
  return `/api/v1/documents/${encodeURIComponent(id)}/original`;
}

export function jobEventsUrl(jobIds: string[]): string {
  return `/api/v1/jobs/events?ids=${jobIds.map(encodeURIComponent).join(",")}`;
}
