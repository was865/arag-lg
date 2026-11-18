"use client";

/** 文書ライブラリの一覧の取得（文書・フォルダ・件数・続きの読み込み・処理中の間の取り直し）。 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useToast } from "@/components/feedback/toast-provider";
import { ApiError } from "@/lib/chat/api";
import { libraryApi, type DocumentOut, type FolderOut } from "@/lib/library/api";
import { docStatus, filterStatuses, type StatusFilter } from "@/lib/library/view";
import { t } from "@/i18n";

const PAGE = 100;

export type LibraryStats = { documents: number; total_bytes: number; by_status: Record<string, number> };

export const errorMessage = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

export function useLibraryList({
  kbId,
  folderId,
  browsing,
  filter,
  search,
}: {
  kbId: string | null;
  folderId: string | null;
  /** フォルダをたどっているか（絞り込み中は KB 全体から探す） */
  browsing: boolean;
  filter: StatusFilter;
  search: string;
}) {
  const push = useToast();
  const [docs, setDocs] = useState<DocumentOut[] | null>(null);
  const [folders, setFolders] = useState<FolderOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [stats, setStats] = useState<LibraryStats | null>(null);

  const listQuery = useMemo(
    () => ({ kbId, folderId: browsing ? folderId : undefined, status: filterStatuses(filter), q: search, limit: PAGE }),
    [kbId, folderId, browsing, filter, search],
  );

  const fetchAll = useCallback(
    () =>
      Promise.all([
        libraryApi.documents(listQuery),
        libraryApi.stats(kbId),
        kbId ? libraryApi.folders(kbId) : Promise.resolve([] as FolderOut[]),
      ]),
    [kbId, listQuery],
  );

  const apply = useCallback(([page, st, fs]: Awaited<ReturnType<typeof fetchAll>>) => {
    setDocs(page.items);
    setCursor(page.next_cursor);
    setStats(st);
    setFolders(fs);
  }, []);

  const reload = useCallback(async () => {
    try {
      apply(await fetchAll());
    } catch (e) {
      setDocs((d) => d ?? []);
      push(errorMessage(e, t.library.listLoadFailed), "error");
    }
  }, [fetchAll, apply, push]);

  // KB を切り替えたら件数・フォルダも消し、フォルダを移ったら前の一覧は見せない
  const [shown, setShown] = useState<{ kb: string | null; folder: string | null } | undefined>(undefined);
  if (shown?.kb !== kbId || shown?.folder !== folderId) {
    if (shown?.kb !== kbId) {
      setStats(null);
      setFolders([]);
    }
    setShown({ kb: kbId, folder: folderId });
    setDocs(null);
    setCursor(null);
  }

  useEffect(() => {
    let alive = true;
    fetchAll().then(
      (r) => alive && apply(r),
      (e: unknown) => {
        if (!alive) return;
        setDocs([]);
        push(errorMessage(e, t.library.listLoadFailed), "error");
      },
    );
    return () => {
      alive = false;
    };
  }, [fetchAll, apply, push]);

  const loadMore = async () => {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await libraryApi.documents({ ...listQuery, cursor });
      setDocs((d) => [...(d ?? []), ...page.items]);
      setCursor(page.next_cursor);
    } catch {
      push(t.library.loadMoreFailed, "error");
    } finally {
      setLoadingMore(false);
    }
  };

  // 処理中の文書がある間は一覧を時々取り直す（キュー外＝別の人や以前のアップロード分も追う）
  const hasBusy = docs?.some((d) => docStatus(d.status).tone === "busy") ?? false;
  useEffect(() => {
    if (!hasBusy) return;
    const timer = window.setInterval(() => void reload(), 5000);
    return () => window.clearInterval(timer);
  }, [hasBusy, reload]);

  return { docs, setDocs, folders, setFolders, stats, cursor, loadingMore, loadMore, reload };
}
