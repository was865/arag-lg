"use client";

/** スレッドの一覧と、名前の変更・星・削除（楽観的に反映し、失敗したら戻す）。 */
import { useCallback, useEffect, useState } from "react";
import { useToast } from "@/components/feedback/toast-provider";
import { useConfirm } from "@/hooks/use-confirm";
import { useT } from "@/i18n/context";
import { interpolate } from "@/i18n/interpolate";
import { chatApi, type ThreadOut } from "@/lib/chat/api";
import type { ThreadSummary } from "@/lib/types";
import { relativeTime } from "@/lib/utils";

export function toSummary(t: ThreadOut): ThreadSummary {
  return { id: t.id, title: t.title, pinned: t.pinned, updated: relativeTime(new Date(t.updated_at)) };
}

export function useThreads({ onDeleted }: { onDeleted: (id: string) => void }) {
  const { t } = useT();
  const push = useToast();
  const { confirm, dialog } = useConfirm();
  const [threads, setThreads] = useState<ThreadOut[]>([]);

  const refreshThreads = useCallback(async () => {
    try {
      setThreads(await chatApi.threads());
    } catch {
      // 一覧の失敗は致命的ではない（次の操作で取り直す）
    }
  }, []);

  useEffect(() => {
    chatApi
      .threads()
      .then(setThreads)
      .catch(() => {});
  }, []);

  const renameThread = async (id: string, title: string) => {
    const prev = threads;
    setThreads((cur) => cur.map((x) => (x.id === id ? { ...x, title } : x)));
    try {
      await chatApi.patchThread(id, { title });
      push(t.feedback.threadRenamed, "success");
    } catch {
      setThreads(prev);
      push(t.feedback.threadRenameFailed, "error");
    }
  };

  const toggleStar = async (id: string, pinned: boolean) => {
    const prev = threads;
    setThreads((cur) => cur.map((x) => (x.id === id ? { ...x, pinned } : x)));
    try {
      await chatApi.patchThread(id, { pinned });
      push(pinned ? t.feedback.starAdded : t.feedback.starRemoved, "success");
      void refreshThreads();
    } catch {
      setThreads(prev);
      push(t.feedback.starUpdateFailed, "error");
    }
  };

  const deleteThread = async (id: string) => {
    const target = threads.find((x) => x.id === id);
    const ok = await confirm({
      title: t.workspace.deleteThreadTitle,
      description: target
        ? interpolate(t.workspace.deleteThreadDescWithTitle, { title: target.title })
        : t.workspace.deleteThreadDescGeneric,
      confirmLabel: t.workspace.deleteThreadConfirm,
      cancelLabel: t.workspace.deleteThreadCancel,
      tone: "danger",
    });
    if (!ok) return;
    try {
      await chatApi.deleteThread(id);
      setThreads((cur) => cur.filter((x) => x.id !== id));
      onDeleted(id);
      push(t.feedback.threadDeleted, "success");
    } catch {
      push(t.feedback.threadDeleteFailed, "error");
    }
  };

  /** 共有の設定などで 1 件を差し替える */
  const replaceThread = (th: ThreadOut) => setThreads((all) => all.map((x) => (x.id === th.id ? th : x)));

  return { threads, refreshThreads, renameThread, toggleStar, deleteThread, replaceThread, confirmDialog: dialog };
}
