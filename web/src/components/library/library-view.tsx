"use client";

/** 文書ライブラリ（チャットと同格の画面）。KB の文書一覧・アップロード・解析の進み具合・名前変更・削除。
 *
 * - 画面のどこにドロップしても、開いている KB（「すべて」なら個人 KB）へ送る。
 * - 解析の進み具合はアップロードキューに出し、終わったら一覧と件数を取り直す。
 * - 削除はごみ箱へ移すだけ（戻せる）なので確認は出さず、トーストで知らせる。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "@/components/icons";
import {
  DocumentsUploadQueue,
  DropOverlay,
} from "@/components/uploads/uploads";
import { useToast } from "@/components/feedback/toast-provider";
import { refreshKbs, useKbs } from "@/hooks/use-kbs";
import { useUploadQueue } from "@/hooks/use-upload-queue";
import { ApiError } from "@/lib/chat/api";
import { ACCEPTED_FILE_TYPES } from "@/lib/constants";
import { getFileMeta } from "@/lib/file-types";
import { libraryApi, originalUrl, type DocumentOut } from "@/lib/library/api";
import {
  docStatus,
  formatBytes,
  formatDate,
  kbLabel,
  filterStatuses,
  uploadTarget,
  type StatusFilter,
  type StatusTone,
} from "@/lib/library/view";
import { cn } from "@/lib/utils";

const PAGE = 100;

const TONE: Record<StatusTone, string> = {
  ok: "text-muted",
  busy: "text-accent",
  danger: "text-danger",
  muted: "text-muted-2",
};

export interface LibraryViewProps {
  /** 表示する KB（null = アクセスできるすべての文書）。 */
  kbId: string | null;
  /** この KB を検索範囲にしてチャットへ戻る。 */
  onAsk: (kbId: string | null) => void;
  /** モバイル: サイドバーを開く。 */
  onOpenMenu: () => void;
}

export function LibraryView({ kbId, onAsk, onOpenMenu }: LibraryViewProps) {
  const push = useToast();
  const { kbs } = useKbs();
  const kb = kbId ? (kbs.find((k) => k.id === kbId) ?? null) : null;
  const target = uploadTarget(kbs, kbId);
  const kbNames = useMemo(
    () => new Map(kbs.map((k) => [k.id, kbLabel(k)])),
    [kbs],
  );

  const [docs, setDocs] = useState<DocumentOut[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [stats, setStats] = useState<{
    documents: number;
    total_bytes: number;
    by_status: Record<string, number>;
  } | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [renaming, setRenaming] = useState<{
    id: string;
    value: string;
  } | null>(null);
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);

  // 名前の絞り込みは入力が落ち着いてからサーバーに問い合わせる（全件が対象）
  const [search, setSearch] = useState("");
  useEffect(() => {
    const t = window.setTimeout(() => setSearch(query.trim()), 250);
    return () => window.clearTimeout(t);
  }, [query]);
  const listQuery = useMemo(
    () => ({ kbId, status: filterStatuses(filter), q: search, limit: PAGE }),
    [kbId, filter, search],
  );

  const reload = useCallback(async () => {
    try {
      const [page, st] = await Promise.all([
        libraryApi.documents(listQuery),
        libraryApi.stats(kbId),
      ]);
      setDocs(page.items);
      setCursor(page.next_cursor);
      setStats(st);
    } catch (e) {
      setDocs((d) => d ?? []);
      push(
        e instanceof ApiError ? e.message : "文書の一覧を取得できませんでした",
        "error",
      );
    }
  }, [kbId, listQuery, push]);

  // KB を切り替えたら読み直す（前の KB の一覧は見せない）
  const [shownKb, setShownKb] = useState<string | null | undefined>(undefined);
  if (shownKb !== kbId) {
    setShownKb(kbId);
    setDocs(null);
    setStats(null);
    setCursor(null);
    setQuery("");
    setSearch("");
    setFilter("all");
  }
  useEffect(() => {
    // 取得は非同期で、結果は then の中で反映する
    let alive = true;
    Promise.all([libraryApi.documents(listQuery), libraryApi.stats(kbId)])
      .then(([page, st]) => {
        if (!alive) return;
        setDocs(page.items);
        setCursor(page.next_cursor);
        setStats(st);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setDocs([]);
        push(
          e instanceof ApiError
            ? e.message
            : "文書の一覧を取得できませんでした",
          "error",
        );
      });
    return () => {
      alive = false;
    };
  }, [kbId, listQuery, push]);

  const queue = useUploadQueue({
    onSettled: () => {
      void reload();
      void refreshKbs();
    },
  });

  const loadMore = async () => {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await libraryApi.documents({ ...listQuery, cursor });
      setDocs((d) => [...(d ?? []), ...page.items]);
      setCursor(page.next_cursor);
    } catch {
      push("続きを読み込めませんでした", "error");
    } finally {
      setLoadingMore(false);
    }
  };

  const startUpload = (list: FileList | File[] | null) => {
    const files = [...(list ?? [])];
    if (!files.length) return;
    if (!target) {
      push("このナレッジベースには追加できません（閲覧のみ）", "error");
      return;
    }
    queue.add(target.id, files);
    // 送信直後の「待機中」を一覧にも出す
    window.setTimeout(() => void reload(), 1200);
  };

  const remove = async (d: DocumentOut) => {
    setDocs((all) => all?.filter((x) => x.id !== d.id) ?? null);
    try {
      await libraryApi.remove(d.id);
      push(`「${d.filename}」をごみ箱に移しました`, "success");
      void refreshKbs();
      void libraryApi.stats(kbId).then(setStats, () => {});
    } catch (e) {
      void reload();
      push(e instanceof ApiError ? e.message : "削除できませんでした", "error");
    }
  };

  const commitRename = async () => {
    if (!renaming) return;
    const { id, value } = renaming;
    const name = value.trim();
    setRenaming(null);
    const before = docs?.find((x) => x.id === id);
    if (!before || !name || name === before.filename) return;
    setDocs(
      (all) =>
        all?.map((x) => (x.id === id ? { ...x, filename: name } : x)) ?? null,
    );
    try {
      await libraryApi.rename(id, name);
    } catch (e) {
      setDocs((all) => all?.map((x) => (x.id === id ? before : x)) ?? null);
      push(
        e instanceof ApiError ? e.message : "名前を変更できませんでした",
        "error",
      );
    }
  };

  const retry = async (d: DocumentOut) => {
    if (!d.job_id) return;
    try {
      await libraryApi.retryJob(d.job_id);
      push(`「${d.filename}」を解析し直します`, "info");
      void reload();
    } catch (e) {
      push(
        e instanceof ApiError ? e.message : "再実行できませんでした",
        "error",
      );
    }
  };

  // 処理中の文書がある間は一覧を時々取り直す（キュー外＝別の人や以前のアップロード分も追う）
  const hasBusy =
    docs?.some((d) => docStatus(d.status).tone === "busy") ?? false;
  useEffect(() => {
    if (!hasBusy) return;
    const t = window.setInterval(() => void reload(), 5000);
    return () => window.clearInterval(t);
  }, [hasBusy, reload]);

  const visible = docs ?? [];
  const busyCount = Object.entries(stats?.by_status ?? {})
    .filter(([s]) => docStatus(s).tone === "busy")
    .reduce((n, [, c]) => n + c, 0);
  const errorCount =
    (stats?.by_status.error ?? 0) + (stats?.by_status.cancelled ?? 0);

  // 画面全体をドロップ先にする
  const dragProps = {
    onDragEnter: (e: React.DragEvent) => {
      if (!e.dataTransfer.types.includes("Files")) return;
      dragDepth.current += 1;
      setDragging(true);
    },
    onDragOver: (e: React.DragEvent) => {
      if (e.dataTransfer.types.includes("Files")) e.preventDefault();
    },
    onDragLeave: () => {
      dragDepth.current = Math.max(0, dragDepth.current - 1);
      if (dragDepth.current === 0) setDragging(false);
    },
    onDrop: (e: React.DragEvent) => {
      e.preventDefault();
      dragDepth.current = 0;
      setDragging(false);
      startUpload(e.dataTransfer.files);
    },
  };

  return (
    <main
      className="grid min-h-0 min-w-0 grid-cols-[minmax(0,1fr)] grid-rows-[auto_auto_1fr] overflow-hidden bg-bg"
      {...dragProps}
    >
      <DropOverlay visible={dragging && Boolean(target)} />
      <header className="sticky top-0 z-[5] flex h-[52px] items-center gap-2 border-b-[0.5px] border-divider bg-bg px-[18px] max-md:px-2.5">
        <button
          className="-ml-1 hidden h-[34px] w-[34px] shrink-0 place-items-center rounded-lg text-fg hover:bg-divider max-md:grid"
          onClick={onOpenMenu}
          aria-label="メニューを開く"
        >
          <Icon name="menu" size={15} />
        </button>
        <div className="flex min-w-0 flex-1 items-baseline gap-2">
          <h1 className="m-0 truncate text-[13.5px] font-semibold text-fg">
            {kbLabel(kb)}
          </h1>
          {stats && (
            <span className="shrink-0 font-mono text-[11px] text-muted max-md:hidden">
              {stats.documents.toLocaleString("ja-JP")} 件 ·{" "}
              {formatBytes(stats.total_bytes)}
            </span>
          )}
          {kb && !kb.canWrite && (
            <span className="shrink-0 rounded-full border-[0.5px] border-divider-strong px-1.5 py-px text-[10px] font-semibold text-muted">
              閲覧のみ
            </span>
          )}
        </div>
        <button
          onClick={() => onAsk(kbId)}
          className="inline-flex h-[30px] items-center gap-1.5 rounded-lg border-[0.5px] border-divider-strong bg-transparent px-2.5 text-[12px] font-medium text-fg hover:bg-divider"
        >
          <Icon name="chat" size={13} />
          <span className="max-md:hidden">
            {kb ? "このナレッジベースに質問" : "質問する"}
          </span>
        </button>
        {target && (
          <button
            onClick={() => fileRef.current?.click()}
            className="inline-flex h-[30px] items-center gap-1.5 rounded-lg border-0 bg-accent px-3 text-[12px] font-semibold text-white hover:brightness-105"
          >
            <Icon name="plus" size={13} />
            追加
          </button>
        )}
        <input
          ref={fileRef}
          type="file"
          multiple
          hidden
          accept={ACCEPTED_FILE_TYPES}
          onChange={(e) => {
            startUpload(e.target.files);
            e.target.value = "";
          }}
        />
      </header>

      <div className="flex flex-wrap items-center gap-2 border-b-[0.5px] border-divider px-[18px] py-2.5 max-md:px-3">
        <label className="flex h-8 min-w-[200px] flex-1 items-center gap-2 rounded-lg border-[0.5px] border-divider-strong bg-surface px-2.5 text-muted focus-within:border-accent max-md:min-w-0">
          <Icon name="search" size={13} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="文書名で絞り込む"
            className="min-w-0 flex-1 border-0 bg-transparent text-[13px] text-fg outline-none placeholder:text-muted-2"
          />
        </label>
        <div
          role="tablist"
          className="flex shrink-0 rounded-lg bg-surface-2 p-0.5"
        >
          {(
            [
              ["all", "すべて", null],
              ["busy", "処理中", busyCount],
              ["error", "失敗", errorCount],
            ] as const
          ).map(([key, label, n]) => (
            <button
              key={key}
              role="tab"
              aria-selected={filter === key}
              onClick={() => setFilter(key)}
              className={cn(
                "inline-flex h-7 items-center gap-1 rounded-md px-2.5 text-[12px] font-medium",
                filter === key
                  ? "bg-surface text-fg shadow-e1"
                  : "text-muted hover:text-fg",
              )}
            >
              {label}
              {n ? (
                <span
                  className={cn(
                    "font-mono text-[10.5px]",
                    key === "error" ? "text-danger" : "text-accent",
                  )}
                >
                  {n}
                </span>
              ) : null}
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 overflow-y-auto">
        <DocumentsUploadQueue
          files={queue.files}
          onRemove={queue.remove}
          onRetry={queue.retry}
          onClear={queue.clear}
        />

        {docs === null ? (
          <div className="grid h-40 place-items-center">
            <span className="h-6 w-6 animate-[ar-spin_0.8s_linear_infinite] rounded-full border-2 border-divider-strong border-t-accent" />
          </div>
        ) : docs.length === 0 && !search && filter === "all" ? (
          <EmptyLibrary
            canUpload={Boolean(target)}
            onPick={() => fileRef.current?.click()}
          />
        ) : (
          <div className="mx-auto max-w-[1100px] px-[18px] pb-10 pt-2 max-md:px-2">
            <div className="grid grid-cols-[minmax(0,1fr)_120px_70px_80px_64px_32px] items-center gap-3 border-b-[0.5px] border-divider px-2 py-2 text-[10.5px] font-semibold uppercase tracking-[0.05em] text-muted-2 max-md:hidden">
              <span>名前</span>
              <span>状態</span>
              <span className="text-right">ページ</span>
              <span className="text-right">サイズ</span>
              <span className="text-right">追加日</span>
              <span />
            </div>
            {visible.length === 0 && (
              <div className="py-10 text-center text-[13px] text-muted">
                条件に合う文書はありません
              </div>
            )}
            {visible.map((d) => {
              const meta = getFileMeta(d.filename);
              const st = docStatus(d.status);
              const busy = st.tone === "busy";
              return (
                <div
                  key={d.id}
                  className="group/row grid grid-cols-[minmax(0,1fr)_120px_70px_80px_64px_32px] items-center gap-3 rounded-lg px-2 py-2 hover:bg-surface-2 max-md:grid-cols-[minmax(0,1fr)_32px] max-md:gap-2"
                >
                  <div className="flex min-w-0 items-center gap-2.5">
                    <span
                      className="grid h-8 w-8 shrink-0 place-items-center rounded-lg"
                      style={{
                        color: meta.color,
                        background: `color-mix(in srgb, ${meta.color} 12%, transparent)`,
                      }}
                    >
                      <Icon name={meta.iconName} size={15} />
                    </span>
                    <div className="min-w-0 flex-1">
                      {renaming?.id === d.id ? (
                        <input
                          autoFocus
                          value={renaming.value}
                          onChange={(e) =>
                            setRenaming({ id: d.id, value: e.target.value })
                          }
                          onBlur={() => void commitRename()}
                          onKeyDown={(e) => {
                            if (e.nativeEvent.isComposing) return;
                            if (e.key === "Enter") void commitRename();
                            if (e.key === "Escape") setRenaming(null);
                          }}
                          className="w-full rounded-md border-[0.5px] border-accent bg-surface px-1.5 py-0.5 text-[13px] text-fg outline-none"
                        />
                      ) : (
                        <a
                          href={originalUrl(d.id)}
                          target="_blank"
                          rel="noopener"
                          title={d.filename}
                          className="block truncate text-[13px] font-medium text-fg no-underline hover:text-accent"
                        >
                          {d.filename}
                        </a>
                      )}
                      <div className="flex items-center gap-1.5 truncate text-[11px] text-muted">
                        {!kbId && (
                          <span className="truncate">
                            {kbNames.get(d.kb_id) ?? ""}
                          </span>
                        )}
                        <span
                          className={cn("hidden max-md:inline", TONE[st.tone])}
                        >
                          {!kbId && "· "}{st.label}
                        </span>
                        <span className="hidden max-md:inline">
                          · {formatDate(d.created_at)}
                        </span>
                        {d.status === "ready" && d.chunk_count > 0 && (
                          <span className="max-md:hidden">
                            {!kbId && "· "}
                            {d.chunk_count.toLocaleString("ja-JP")} チャンク
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <span
                    className={cn(
                      "inline-flex items-center gap-1.5 text-[12px] max-md:hidden",
                      TONE[st.tone],
                    )}
                  >
                    {busy && (
                      <span className="h-2.5 w-2.5 animate-spin-fast rounded-full border-[1.5px] border-divider-strong border-t-accent" />
                    )}
                    {st.tone === "ok" && (
                      <span className="h-1.5 w-1.5 rounded-full bg-[#3c9a5f]" />
                    )}
                    {st.label}
                    {st.tone === "danger" && d.writable && d.job_id && (
                      <button
                        onClick={() => void retry(d)}
                        className="ml-0.5 rounded px-1 text-[11px] font-semibold text-accent hover:underline"
                      >
                        再実行
                      </button>
                    )}
                  </span>
                  <span className="text-right font-mono text-[11.5px] text-muted max-md:hidden">
                    {d.page_count ?? "—"}
                  </span>
                  <span className="text-right font-mono text-[11.5px] text-muted max-md:hidden">
                    {formatBytes(d.size)}
                  </span>
                  <span className="text-right font-mono text-[11.5px] text-muted max-md:hidden">
                    {formatDate(d.created_at)}
                  </span>
                  <RowMenu
                    open={menuFor === d.id}
                    onToggle={(o) => setMenuFor(o ? d.id : null)}
                    items={[
                      {
                        label: "原本を開く",
                        icon: "external",
                        onClick: () =>
                          window.open(originalUrl(d.id), "_blank", "noopener"),
                      },
                      {
                        label: "ダウンロード",
                        icon: "download",
                        onClick: () => {
                          const a = document.createElement("a");
                          a.href = originalUrl(d.id);
                          a.download = d.filename;
                          a.click();
                        },
                      },
                      ...(d.writable
                        ? [
                            {
                              label: "名前を変更",
                              icon: "pencil" as const,
                              onClick: () =>
                                setRenaming({ id: d.id, value: d.filename }),
                            },
                            {
                              label: "ごみ箱へ移動",
                              icon: "trash" as const,
                              danger: true,
                              onClick: () => void remove(d),
                            },
                          ]
                        : []),
                    ]}
                  />
                </div>
              );
            })}
            {cursor && (
              <div className="pt-4 text-center">
                <button
                  onClick={() => void loadMore()}
                  disabled={loadingMore}
                  className="h-8 rounded-lg border-[0.5px] border-divider-strong bg-surface px-4 text-[12.5px] text-fg hover:bg-surface-2 disabled:opacity-60"
                >
                  {loadingMore ? "読み込み中…" : "さらに読み込む"}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  );
}

interface MenuItem {
  label: string;
  icon: "external" | "download" | "pencil" | "trash";
  onClick: () => void;
  danger?: boolean;
}

function RowMenu({
  open,
  onToggle,
  items,
}: {
  open: boolean;
  onToggle: (open: boolean) => void;
  items: MenuItem[];
}) {
  return (
    <span className="relative justify-self-end">
      <button
        aria-label="操作メニュー"
        onClick={() => onToggle(!open)}
        className={cn(
          "grid h-7 w-7 place-items-center rounded-md text-muted hover:bg-divider hover:text-fg",
          !open &&
            "opacity-0 focus-visible:opacity-100 group-hover/row:opacity-100 max-md:opacity-100",
        )}
      >
        <Icon name="more" size={15} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => onToggle(false)} />
          <div
            role="menu"
            className="absolute right-0 top-8 z-30 w-[168px] animate-pop-in overflow-hidden rounded-[10px] border-[0.5px] border-divider-strong bg-surface p-1 shadow-e2"
          >
            {items.map((it) => (
              <button
                key={it.label}
                role="menuitem"
                onClick={() => {
                  onToggle(false);
                  it.onClick();
                }}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[12.5px] font-medium",
                  it.danger
                    ? "text-danger hover:bg-danger-soft"
                    : "text-fg hover:bg-divider",
                )}
              >
                <Icon name={it.icon} size={13} />
                {it.label}
              </button>
            ))}
          </div>
        </>
      )}
    </span>
  );
}

function EmptyLibrary({
  canUpload,
  onPick,
}: {
  canUpload: boolean;
  onPick: () => void;
}) {
  return (
    <div className="grid place-items-center px-6 py-16">
      <button
        type="button"
        disabled={!canUpload}
        onClick={onPick}
        className="flex w-full max-w-[520px] flex-col items-center gap-3 rounded-[16px] border-2 border-dashed border-divider-strong bg-surface-2 px-8 py-12 text-center enabled:hover:border-accent enabled:hover:bg-accent-soft disabled:cursor-default"
      >
        <span className="grid h-12 w-12 place-items-center rounded-[14px] bg-accent-soft text-accent">
          <Icon name="database" size={20} />
        </span>
        <span className="text-[15px] font-semibold text-fg">
          {canUpload
            ? "文書を追加して、質問に使いましょう"
            : "このナレッジベースにはまだ文書がありません"}
        </span>
        {canUpload && (
          <span className="text-[12.5px] leading-[1.6] text-muted">
            ここにドラッグ＆ドロップするか、クリックして選んでください。
            <br />
            PDF・Word・Excel・PowerPoint・テキスト・画像に対応。追加すると自動で解析され、検索できるようになります。
          </span>
        )}
      </button>
    </div>
  );
}
