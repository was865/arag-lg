"use client";

/** 文書ライブラリのアップロードキュー（送信の進み具合 → 解析ジョブの段階）。
 *
 * - 送信は XHR で 3 本まで並行し、ファイルごとに進み具合を出す。
 * - 送り終えたら解析ジョブを GET /v1/jobs/events（SSE）で 1 本にまとめて追う。対象が増えたら繋ぎ直す。
 * - 解析が終わった・失敗したら onSettled を呼ぶ（一覧と件数の取り直しに使う）。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/chat/api";
import { jobEventsUrl, libraryApi, uploadFile } from "@/lib/library/api";
import {
  applyJobEvent,
  applyUploadItem,
  JOB_TERMINAL,
  pendingJobIds,
  type JobEvent,
} from "@/lib/library/jobs";
import type { StagedFile } from "@/lib/types";
import { uid } from "@/lib/utils";

const CONCURRENCY = 3;

interface Pending {
  file: File;
  kbId: string;
  abort: AbortController;
}

export function useUploadQueue({ onSettled }: { onSettled?: () => void } = {}) {
  const [files, setFiles] = useState<StagedFile[]>([]);
  const sources = useRef(new Map<string, Pending>());
  const waiting = useRef<string[]>([]);
  const active = useRef(0);
  const settled = useRef(onSettled);
  useEffect(() => {
    settled.current = onSettled;
  });

  const patch = useCallback((id: string, fn: (f: StagedFile) => StagedFile) => {
    setFiles((all) => all.map((f) => (f.id === id ? fn(f) : f)));
  }, []);

  // 送信の開始。完了時に自分を呼び直すので ref 経由にする
  const pumpRef = useRef<() => void>(() => {});
  useEffect(() => {
    pumpRef.current = () => {
      while (active.current < CONCURRENCY && waiting.current.length) {
        const id = waiting.current.shift()!;
        const src = sources.current.get(id);
        if (!src) continue;
        active.current += 1;
        uploadFile(
          src.kbId,
          src.file,
          (r) => patch(id, (f) => ({ ...f, progress: Math.round(r * 100) })),
          src.abort.signal,
        )
          .then((res) => {
            const item = res.items[0];
            if (!item)
              throw new ApiError(500, "empty", "アップロードの結果が空でした");
            patch(id, (f) => applyUploadItem(f, item));
            if (!item.job_id) settled.current?.();
          })
          .catch((e: unknown) => {
            const message =
              e instanceof ApiError ? e.message : "アップロードに失敗しました";
            patch(id, (f) => ({ ...f, status: "error", error: message }));
          })
          .finally(() => {
            active.current -= 1;
            pumpRef.current();
          });
      }
    };
  }, [patch]);
  const pump = useCallback(() => pumpRef.current(), []);

  /** ファイルを KB に送る。 */
  const add = useCallback(
    (kbId: string, list: File[]) => {
      const staged = list.map((file) => {
        const id = uid("up_");
        sources.current.set(id, { file, kbId, abort: new AbortController() });
        waiting.current.push(id);
        return {
          id,
          name: file.name,
          size: file.size,
          status: "uploading",
          progress: 0,
        } satisfies StagedFile;
      });
      setFiles((all) => [...staged, ...all]);
      pump();
    },
    [pump],
  );

  /** 送信中なら取り消し、それ以外は一覧から外す（解析は API 側で続く）。 */
  const remove = useCallback((id: string) => {
    const src = sources.current.get(id);
    waiting.current = waiting.current.filter((x) => x !== id);
    src?.abort.abort();
    sources.current.delete(id);
    setFiles((all) => all.filter((f) => f.id !== id));
  }, []);

  /** 失敗したものをやり直す（解析の失敗はジョブを再実行、送信の失敗は送り直す）。 */
  const retry = useCallback(
    (id: string) => {
      const f = files.find((x) => x.id === id);
      if (!f) return;
      if (f.jobId) {
        patch(id, (x) => ({
          ...x,
          status: "queued",
          error: undefined,
          progress: 0,
        }));
        libraryApi.retryJob(f.jobId).catch((e: unknown) => {
          patch(id, (x) => ({
            ...x,
            status: "error",
            error: e instanceof ApiError ? e.message : "再実行できませんでした",
          }));
        });
      } else if (sources.current.has(id)) {
        sources.current.get(id)!.abort = new AbortController();
        patch(id, (x) => ({
          ...x,
          status: "uploading",
          error: undefined,
          progress: 0,
        }));
        waiting.current.push(id);
        pump();
      }
    },
    [files, patch, pump],
  );

  /** 終わったもの（完了・重複）を一覧から消す。 */
  const clear = useCallback(() => {
    setFiles((all) => {
      const keep = all.filter(
        (f) => f.status !== "ready" && f.status !== "skipped",
      );
      for (const f of all) if (!keep.includes(f)) sources.current.delete(f.id);
      return keep;
    });
  }, []);

  // 解析ジョブの購読。対象の集合が変わったら繋ぎ直す
  const pendingKey = pendingJobIds(files).join(",");
  useEffect(() => {
    if (!pendingKey) return;
    const es = new EventSource(jobEventsUrl(pendingKey.split(",")));
    es.addEventListener("job", (e) => {
      let ev: JobEvent;
      try {
        ev = JSON.parse((e as MessageEvent<string>).data) as JobEvent;
      } catch {
        return;
      }
      setFiles((all) => all.map((f) => applyJobEvent(f, ev)));
      if (JOB_TERMINAL.has(ev.status)) settled.current?.();
    });
    return () => es.close();
  }, [pendingKey]);

  useEffect(() => {
    const map = sources.current;
    return () => {
      for (const s of map.values()) s.abort.abort();
    };
  }, []);

  const busy = files.some(
    (f) =>
      f.status === "uploading" ||
      f.status === "queued" ||
      f.status === "processing",
  );
  return { files, add, remove, retry, clear, busy };
}
