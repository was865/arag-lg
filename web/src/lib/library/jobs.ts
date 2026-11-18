/** アップロード → 解析ジョブの進み具合を StagedFile（旧版のキュー表示の view model）に写す。 */
import type { components } from "@/lib/api/schema";
import type { IngestStage, StagedFile } from "@/lib/types";
import { t } from "@/i18n";

export type UploadItem = components["schemas"]["UploadItem"];

/** GET /v1/jobs/events の `event: job` の中身。 */
export interface JobEvent {
  job_id: string;
  document_id: string;
  stage: string;
  progress: number;
  stage_detail?: string | null;
  status: string;
  error?: string | null;
  page_count?: number | null;
  chunk_count?: number | null;
}

const STAGES = new Set<IngestStage>(["parsing", "chunking", "embedding", "indexing", "ready"]);
export const JOB_TERMINAL = new Set(["ready", "error", "cancelled"]);

/** アップロード応答を当てる。
 * - duplicate: 同じ KB に同じ内容が既にある → 取り込まない（skipped）
 * - skipped: 同じ内容を別の場所で解析済み（ジョブ無し → 即 ready）か解析中（ジョブを追う）
 * - queued: 新しく解析する */
export function applyUploadItem(f: StagedFile, item: UploadItem): StagedFile {
  const base = { ...f, documentId: item.document_id, jobId: item.job_id ?? undefined };
  if (item.status === "duplicate") {
    return { ...base, status: "skipped", progress: 100, stageDetail: t.library.jobDuplicate };
  }
  if (!item.job_id) return { ...base, status: "ready", stage: "ready", progress: 100 };
  return { ...base, status: "queued", progress: 0 };
}

/** ジョブの進捗イベントを当てる。順序が前後しても、終わったものを戻さない。 */
export function applyJobEvent(f: StagedFile, ev: JobEvent): StagedFile {
  if (f.jobId !== ev.job_id || f.status === "ready" || f.status === "error") return f;
  const stage = STAGES.has(ev.stage as IngestStage) ? (ev.stage as IngestStage) : f.stage;
  if (ev.status === "ready") {
    return {
      ...f,
      status: "ready",
      stage: "ready",
      progress: 100,
      pages: ev.page_count ?? f.pages,
      chunks: ev.chunk_count ?? f.chunks,
    };
  }
  if (ev.status === "error" || ev.status === "cancelled") {
    return { ...f, status: "error", error: ev.error || (ev.status === "cancelled" ? t.library.jobCancelled : t.library.jobFailed) };
  }
  return {
    ...f,
    status: ev.status === "queued" ? "queued" : "processing",
    stage,
    stageDetail: ev.stage_detail ?? f.stageDetail,
    progress: Math.max(f.progress, Math.min(99, ev.progress ?? 0)),
    pages: ev.page_count ?? f.pages,
  };
}

/** まだ解析が終わっていないジョブ ID（購読の対象）。 */
export function pendingJobIds(files: StagedFile[]): string[] {
  return files.filter((f) => f.jobId && (f.status === "queued" || f.status === "processing")).map((f) => f.jobId!);
}
