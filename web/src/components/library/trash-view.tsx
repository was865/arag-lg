"use client";

/** ごみ箱。削除した文書・フォルダ・ナレッジベースを一覧し、元に戻す／完全に削除する。
 * 完全な削除は取り消せないので確認を出す（文書のみ。フォルダ・KB は期限が来たら自動で消える）。 */
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

const KIND_LABEL: Record<TrashItem["kind"], string> = {
  document: "文書",
  folder: "フォルダ",
  kb: "ナレッジベース",
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
        e instanceof ApiError ? e.message : "ごみ箱を取得できませんでした",
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
          e instanceof ApiError ? e.message : "ごみ箱を取得できませんでした",
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
      push(`「${item.name}」を元に戻しました`, "success");
      void refreshKbs();
    } catch (e) {
      push(e instanceof ApiError ? e.message : "元に戻せませんでした", "error");
      void reload();
    } finally {
      setBusyId(null);
    }
  };

  const purge = async (item: TrashItem) => {
    const ok = await confirm({
      title: `「${item.name}」を完全に削除しますか？`,
      description:
        item.kind === "folder"
          ? "中のフォルダと文書も含め、元の文書と検索用のデータがすべて消えます。この操作は取り消せません。"
          : "元の文書と検索用のデータがすべて消えます。この操作は取り消せません。",
      confirmLabel: "完全に削除",
      tone: "danger",
    });
    if (!ok) return;
    setBusyId(item.id);
    try {
      await libraryApi.purge(item);
      setItems((all) => all?.filter((x) => x.id !== item.id) ?? null);
      // フォルダは中の（別に消した）項目も消えるので取り直す
      if (item.kind === "folder") void reload();
      push(`「${item.name}」を完全に削除しました`, "success");
    } catch (e) {
      push(e instanceof ApiError ? e.message : "削除できませんでした", "error");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <main className="grid min-h-0 min-w-0 grid-cols-[minmax(0,1fr)] grid-rows-[auto_1fr] overflow-hidden bg-bg">
      <header className="sticky top-0 z-[5] flex h-[52px] items-center gap-2 border-b-[0.5px] border-divider bg-bg px-[18px] max-md:px-2.5">
        <IconButton
          label="メニューを開く"
          tooltip={false}
          icon="menu"
          iconSize={15}
          onClick={onOpenMenu}
          className="-ml-1 hidden h-[34px] w-[34px] text-fg max-md:inline-flex"
        />
        <h1 className="m-0 flex-1 truncate text-body font-semibold text-fg">
          ごみ箱
        </h1>
        {items && items.length > 0 && (
          <span className="font-mono text-caption text-muted">
            {items.length} 件
          </span>
        )}
      </header>

      <div className="min-h-0 overflow-y-auto">
        <div className="mx-auto max-w-[900px] px-[18px] pb-10 pt-4 max-md:px-2">
          <p className="m-0 mb-3 px-2 text-footnote leading-[1.6] text-muted">
            ごみ箱の項目は検索の対象外です。期限が来ると自動で完全に削除されます。
          </p>
          {items === null ? (
            <ListSkeleton />
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-16 text-center">
              <span className="grid h-11 w-11 place-items-center rounded-[12px] bg-surface-2 text-muted">
                <Icon name="trash" size={18} />
              </span>
              <span className="text-body font-medium text-fg">
                ごみ箱は空です
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
                  <span
                    className="grid h-8 w-8 shrink-0 place-items-center rounded-control bg-surface-2 text-muted"
                    style={
                      icon.color
                        ? {
                            color: icon.color,
                            background: `color-mix(in srgb, ${icon.color} 12%, transparent)`,
                          }
                        : undefined
                    }
                  >
                    <Icon name={icon.name} size={15} />
                  </span>
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
                        : ""}{" "}
                      · {formatDate(item.deleted_at)} に削除 ·{" "}
                      <span
                        className={
                          item.remaining_days <= 3 ? "text-danger" : undefined
                        }
                      >
                        あと {item.remaining_days} 日で消去
                      </span>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5 max-md:ml-11">
                    <Button variant="secondary" size="sm"
                      disabled={busy}
                      onClick={() => void restore(item)}
                    >
                      <Icon name="refresh" size={12} />
                      元に戻す
                    </Button>
                    {item.kind !== "kb" && item.purgeable && (
                      <Button variant="danger-ghost" size="sm"
                        disabled={busy}
                        onClick={() => void purge(item)}
                      >
                        完全に削除
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
