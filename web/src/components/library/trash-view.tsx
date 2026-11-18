"use client";

/** ごみ箱。削除した文書・フォルダ・ナレッジベースを一覧し、元に戻す／完全に削除する。
 * 完全な削除は取り消せないので確認を出す（文書のみ。フォルダ・KB は期限が来たら自動で消える）。 */
import { FileTile } from "@/components/ui/file-tile";
import { ListSkeleton } from "@/components/ui/skeleton";
import { useCallback, useEffect, useState } from "react";
import { Icon, type IconName } from "@/components/icons";
import { useToast } from "@/components/feedback/toast-provider";
import { useConfirm } from "@/hooks/use-confirm";
import { refreshKbs } from "@/hooks/use-kbs";
import { ApiError } from "@/lib/chat/api";
import { getFileMeta } from "@/lib/file-types";
import { libraryApi, type TrashItem } from "@/lib/library/api";
import { formatDate } from "@/lib/library/view";
import { IconButton, Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { interpolate } from "@/i18n/interpolate";

const KIND_LABEL: Record<TrashItem["kind"], string> = {
  document: t.trash.kindDocument,
  folder: t.trash.kindFolder,
  kb: t.trash.kindKb,
};

function kindIcon(item: TrashItem): { name: IconName; color?: string } {
  if (item.kind === "folder") return { name: "folder" };
  if (item.kind === "kb") return { name: "database" };
  const meta = getFileMeta(item.name);
  return { name: meta.iconName, color: meta.color };
}

export function TrashView({ onOpenMenu }: { onOpenMenu: () => void }) {
  const push = useToast();
  const { confirm, dialog } = useConfirm();
  const [items, setItems] = useState<TrashItem[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setItems(await libraryApi.trash());
    } catch (e) {
      setItems((x) => x ?? []);
      push(
        e instanceof ApiError ? e.message : t.trash.loadFailed,
        "error",
      );
    }
  }, [push]);

  useEffect(() => {
    let alive = true;
    libraryApi.trash().then(
      (x) => alive && setItems(x),
      (e: unknown) => {
        if (!alive) return;
        setItems([]);
        push(
          e instanceof ApiError ? e.message : t.trash.loadFailed,
          "error",
        );
      },
    );
    return () => {
      alive = false;
    };
  }, [push]);

  const restore = async (item: TrashItem) => {
    setBusyId(item.id);
    try {
      await libraryApi.restore(item);
      setItems((all) => all?.filter((x) => x.id !== item.id) ?? null);
      push(interpolate(t.trash.restored, { name: item.name }), "success");
      void refreshKbs();
    } catch (e) {
      push(e instanceof ApiError ? e.message : t.trash.restoreFailed, "error");
      void reload();
    } finally {
      setBusyId(null);
    }
  };

  const purge = async (item: TrashItem) => {
    const ok = await confirm({
      title: interpolate(t.trash.purgeTitle, { name: item.name }),
      description:
        item.kind === "folder"
          ? t.trash.purgeBodyFolder
          : t.trash.purgeBody,
      confirmLabel: t.trash.purgeConfirm,
      tone: "danger",
    });
    if (!ok) return;
    setBusyId(item.id);
    try {
      await libraryApi.purge(item);
      setItems((all) => all?.filter((x) => x.id !== item.id) ?? null);
      // フォルダは中の（別に消した）項目も消えるので取り直す
      if (item.kind === "folder") void reload();
      push(interpolate(t.trash.purged, { name: item.name }), "success");
    } catch (e) {
      push(e instanceof ApiError ? e.message : t.library.deleteFailed, "error");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <main className="grid min-h-0 min-w-0 grid-cols-[minmax(0,1fr)] grid-rows-[auto_1fr] overflow-hidden bg-bg">
      <header className="sticky top-0 z-[5] flex h-[52px] items-center gap-2 border-b-[0.5px] border-divider bg-bg px-[18px] max-md:px-2.5">
        <IconButton
          label={t.common.openMenu}
          tooltip={false}
          icon="menu"
          iconSize={15}
          onClick={onOpenMenu}
          className="-ml-1 hidden h-[34px] w-[34px] text-fg max-md:inline-flex"
        />
        <h1 className="m-0 flex-1 truncate text-body font-semibold text-fg">
          {t.trash.title}
        </h1>
        {items && items.length > 0 && (
          <span className="font-mono text-caption text-muted">
            {interpolate(t.trash.count, { length: items.length })}
          </span>
        )}
      </header>

      <div className="min-h-0 overflow-y-auto">
        <div className="mx-auto max-w-[900px] px-[18px] pb-10 pt-4 max-md:px-2">
          <p className="m-0 mb-3 px-2 text-footnote leading-[1.6] text-muted">
            {t.trash.note}
          </p>
          {items === null ? (
            <ListSkeleton />
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-16 text-center">
              <span className="grid h-11 w-11 place-items-center rounded-[12px] bg-surface-2 text-muted">
                <Icon name="trash" size={18} />
              </span>
              <span className="text-body font-medium text-fg">
                {t.trash.empty}
              </span>
            </div>
          ) : (
            items.map((item) => {
              const icon = kindIcon(item);
              const busy = busyId === item.id;
              return (
                <div
                  key={`${item.kind}:${item.id}`}
                  className="flex items-center gap-3 rounded-control px-2 py-2.5 hover:bg-surface-2 max-md:flex-wrap"
                >
                  <FileTile icon={icon.name} color={icon.color} />
                  <div className="min-w-0 flex-1">
                    <div
                      className="truncate text-body font-medium text-fg"
                      title={item.name}
                    >
                      {item.name}
                    </div>
                    <div className="truncate text-caption text-muted">
                      {KIND_LABEL[item.kind]}
                      {item.kind !== "kb" && item.kb_name
                        ? ` · ${item.kb_name}`
                        : ""}{interpolate(t.trash.deletedAt, { deleted_at: formatDate(item.deleted_at) })}
                      <span
                        className={
                          item.remaining_days <= 3 ? "text-danger" : undefined
                        }
                      >
                        {interpolate(t.trash.remaining, { remaining_days: item.remaining_days })}
                      </span>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5 max-md:ml-11">
                    <Button variant="secondary" size="sm"
                      disabled={busy}
                      onClick={() => void restore(item)}
                    >
                      <Icon name="refresh" size={12} />
                      {t.trash.restore}
                    </Button>
                    {item.kind !== "kb" && item.purgeable && (
                      <Button variant="danger-ghost" size="sm"
                        disabled={busy}
                        onClick={() => void purge(item)}
                      >
                        {t.trash.purgeConfirm}
                      </Button>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
      {dialog}
    </main>
  );
}
