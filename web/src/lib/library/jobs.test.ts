import { describe, expect, it } from "vitest";
import { applyJobEvent, applyUploadItem, pendingJobIds } from "@/lib/library/jobs";
import type { StagedFile } from "@/lib/types";

const staged: StagedFile = { id: "u1", name: "規程.pdf", size: 10, status: "uploading", progress: 40 };
const ev = (over: Record<string, unknown>) => ({
  job_id: "j1",
  document_id: "d1",
  stage: "parsing",
  progress: 10,
  status: "running",
  ...over,
});

describe("applyUploadItem", () => {
  it("新しい内容は queued、解析済みの内容は即 ready、同じ KB の重複は skipped", () => {
    expect(applyUploadItem(staged, { filename: "規程.pdf", document_id: "d1", job_id: "j1", status: "queued" })).toMatchObject({
      status: "queued",
      jobId: "j1",
      documentId: "d1",
      progress: 0,
    });
    expect(applyUploadItem(staged, { filename: "規程.pdf", document_id: "d1", job_id: null, status: "skipped" })).toMatchObject({
      status: "ready",
      stage: "ready",
      progress: 100,
    });
    // 別の場所で解析中ならそのジョブを追う
    expect(applyUploadItem(staged, { filename: "規程.pdf", document_id: "d1", job_id: "j9", status: "skipped" }).status).toBe("queued");
    expect(applyUploadItem(staged, { filename: "規程.pdf", document_id: "d0", job_id: null, status: "duplicate" }).status).toBe("skipped");
  });
});

describe("applyJobEvent", () => {
  const queued = applyUploadItem(staged, { filename: "規程.pdf", document_id: "d1", job_id: "j1", status: "queued" });

  it("段階と進捗を写し、完了でページ数・チャンク数を確定する", () => {
    const p = applyJobEvent(queued, ev({ stage: "embedding", progress: 60, stage_detail: "埋め込み生成" }));
    expect(p).toMatchObject({ status: "processing", stage: "embedding", progress: 60, stageDetail: "埋め込み生成" });
    const done = applyJobEvent(p, ev({ stage: "ready", status: "ready", progress: 100, page_count: 4, chunk_count: 12 }));
    expect(done).toMatchObject({ status: "ready", progress: 100, pages: 4, chunks: 12 });
  });

  it("失敗は理由つきで error、別ジョブのイベントは無視、終わったものは戻さない", () => {
    expect(applyJobEvent(queued, ev({ status: "error", error: "壊れた PDF" }))).toMatchObject({ status: "error", error: "壊れた PDF" });
    expect(applyJobEvent(queued, ev({ job_id: "other", stage: "indexing" }))).toBe(queued);
    const done = applyJobEvent(queued, ev({ status: "ready", stage: "ready" }));
    expect(applyJobEvent(done, ev({ stage: "parsing" }))).toBe(done);
  });

  it("進捗は後戻りしない", () => {
    const a = applyJobEvent(queued, ev({ stage: "chunking", progress: 50 }));
    expect(applyJobEvent(a, ev({ stage: "chunking", progress: 30 })).progress).toBe(50);
  });
});

describe("pendingJobIds", () => {
  it("解析待ち・解析中のジョブだけ", () => {
    const files: StagedFile[] = [
      { ...staged, id: "a", jobId: "j1", status: "queued" },
      { ...staged, id: "b", jobId: "j2", status: "ready" },
      { ...staged, id: "c", jobId: "j3", status: "processing" },
      { ...staged, id: "d", status: "uploading" },
    ];
    expect(pendingJobIds(files)).toEqual(["j1", "j3"]);
  });
});
