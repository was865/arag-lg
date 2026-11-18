"use client";

/** 文書ライブラリ（チャットと同格の画面）。KB の文書一覧・フォルダ・アップロード・解析の進み具合・名前変更・移動・削除。
 *
 * - 画面のどこにドロップしても、開いている KB のフォルダ（「すべて」なら個人 KB）へ送る。
 * - KB を開いているときはフォルダをたどれる。名前・状態で絞り込むと KB 全体から探す。
 * - 文書はフォルダ行・パンくずへドラッグするか、メニューの「移動」で移せる。
 * - 解析の進み具合はアップロードキューに出し、終わったら一覧と件数を取り直す。
 * - 文書の削除はごみ箱へ移すだけ（戻せる）なので確認は出さず、トーストで知らせる。
 *   フォルダは中身ごと移るので確認を出す。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { ListSkeleton } from "@/components/ui/skeleton";
import { Button, IconButton } from "@/components/ui/button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/menu";
import { SearchField } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Segmented } from "@/components/ui/segmented";
import { Icon } from "@/components/icons";
import { DocumentsUploadQueue, DropOverlay } from "@/components/uploads/uploads";
import { useToast } from "@/components/feedback/toast-provider";
import { MoveDialog } from "@/components/library/move-dialog";
import { LibraryOverview } from "@/components/library/library-overview";
import { BulkBar, DOC_MIME, EmptyLibrary } from "@/components/library/library-parts";
import { DocumentRow, FolderRow, ListHeader, NewFolderRow, type RenameState } from "@/components/library/library-rows";
import { errorMessage, useLibraryList } from "@/components/library/use-library-list";
import { useLibraryUpload } from "@/components/library/use-library-upload";
import { KbShareButton } from "@/components/access/kb-share-button";
import { useConfirm } from "@/hooks/use-confirm";
import { refreshKbs, useKbs } from "@/hooks/use-kbs";
import { ACCEPTED_FILE_TYPES } from "@/lib/constants";
import { libraryApi, type DocumentOut, type FolderOut } from "@/lib/library/api";
import { chunk, selectRange, toggleId } from "@/lib/library/selection";
import { breadcrumb, childFolders } from "@/lib/library/folders";
import { docStatus, formatBytes, kbLabel, uploadTarget, type StatusFilter } from "@/lib/library/view";
import { cn } from "@/lib/utils";
import { t } from "@/i18n";
import { interpolate } from "@/i18n/interpolate";

export interface LibraryViewProps {
  /** 表示する KB（null = アクセスできるすべての文書）。 */
  kbId: string | null;
  /** 開いているフォルダ（null = KB のルート）。 */
  folderId: string | null;
  /** フォルダを開く（null = KB のルートへ）。 */
  onOpenFolder: (folderId: string | null) => void;
  /** この KB を検索範囲にしてチャットへ戻る。 */
  onAsk: (kbId: string | null) => void;
  /** 文書ビューアを開く。 */
  onOpenDocument: (doc: DocumentOut) => void;
  /** モバイル: サイドバーを開く。 */
  onOpenMenu: () => void;
}

export function LibraryView({ kbId, folderId, onOpenFolder, onAsk, onOpenDocument, onOpenMenu }: LibraryViewProps) {
  const push = useToast();
  const { confirm, dialog } = useConfirm();
  const { kbs } = useKbs();
  const kb = kbId ? (kbs.find((k) => k.id === kbId) ?? null) : null;
  const target = uploadTarget(kbs, kbId);
  const canEditFolders = Boolean(kb?.canWrite && kb.status !== "archived");
  const kbNames = useMemo(() => new Map(kbs.map((k) => [k.id, kbLabel(k)])), [kbs]);

  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [renaming, setRenaming] = useState<{ kind: "doc" | "folder"; id: string; value: string } | null>(null);
  const [creating, setCreating] = useState<string | null>(null);
  const [moving, setMoving] = useState<DocumentOut | null>(null);
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [dropOn, setDropOn] = useState<string | null>(null);
  // 複数選択（specs/009-library-bulk）
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [anchor, setAnchor] = useState<string | null>(null);
  const [bulkMoving, setBulkMoving] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const dirRef = useRef<HTMLInputElement>(null);
  const [addMenu, setAddMenu] = useState(false);

  // 名前の絞り込みは入力が落ち着いてからサーバーに問い合わせる（全件が対象）
  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(query.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  // フォルダをたどるのは KB を開いていて、絞り込んでいないときだけ
  const browsing = Boolean(kbId) && !search && filter === "all";
  const { docs, setDocs, folders, setFolders, stats, cursor, loadingMore, loadMore, reload } = useLibraryList({
    kbId,
    folderId,
    browsing,
    filter,
    search,
  });
  const { queue, dragging, dropZone, startUpload, startFolderUpload } = useLibraryUpload({ target, kbId, folderId, reload });

  // KB を切り替えたら絞り込みを戻し、場所や絞り込みを変えたら選択・入力中の名前をやめる
  const [shownKb, setShownKb] = useState<string | null | undefined>(undefined);
  const [shownFolder, setShownFolder] = useState<string | null | undefined>(undefined);
  const selKey = `${kbId}|${folderId}|${filter}|${search}`;
  const [shownSelKey, setShownSelKey] = useState(selKey);
  if (shownSelKey !== selKey) {
    setShownSelKey(selKey);
    setSelecting(false);
    setSelected(new Set());
    setAnchor(null);
  }
  if (shownKb !== kbId || shownFolder !== folderId) {
    if (shownKb !== kbId) {
      setQuery("");
      setSearch("");
      setFilter("all");
    }
    setShownKb(kbId);
    setShownFolder(folderId);
    setCreating(null);
    setRenaming(null);
  }

  // ── 文書の操作 ─────────────────────────────────────────────────────
  const removeDoc = async (d: DocumentOut) => {
    setDocs((all) => all?.filter((x) => x.id !== d.id) ?? null);
    try {
      await libraryApi.remove(d.id);
      push(interpolate(t.library.docTrashed, { filename: d.filename }), "success");
      void refreshKbs();
      void reload();
    } catch (e) {
      void reload();
      push(errorMessage(e, t.library.deleteFailed), "error");
    }
  };

  const moveDoc = async (docId: string, to: string | null) => {
    const d = docs?.find((x) => x.id === docId);
    if (!d || d.folder_id === to) return;
    // いまの一覧（このフォルダ）から外れるなら先に消す
    if (browsing) setDocs((all) => all?.filter((x) => x.id !== docId) ?? null);
    try {
      await libraryApi.moveDocuments([docId], to);
      const name = to ? (folders.find((f) => f.id === to)?.name ?? t.library.folder) : kbLabel(kb);
      push(interpolate(t.library.docMoved, { filename: d.filename, name }), "success");
    } catch (e) {
      push(errorMessage(e, t.library.moveFailed), "error");
    }
    void reload();
  };

  const retry = async (d: DocumentOut) => {
    if (!d.job_id) return;
    try {
      await libraryApi.retryJob(d.job_id);
      push(interpolate(t.library.reparsing, { filename: d.filename }), "info");
      void reload();
    } catch (e) {
      push(errorMessage(e, t.library.retryFailed), "error");
    }
  };

  // ── まとめて操作 ─────────────────────────────────────────────────────
  const endSelection = () => {
    setSelecting(false);
    setSelected(new Set());
    setAnchor(null);
  };

  const pickRow = (id: string, shift: boolean) => {
    setSelecting(true);
    setSelected((sel) =>
      shift ? selectRange(sel, docs?.map((x) => x.id) ?? [], anchor, id) : toggleId(sel, id),
    );
    setAnchor(id);
  };

  const removeSelected = async () => {
    const ids = [...selected];
    const ok = await confirm({
      title: interpolate(t.library.bulkTrashTitle, { length: ids.length }),
      description: t.library.bulkTrashBody,
      confirmLabel: t.library.trashConfirm,
      tone: "danger",
    });
    if (!ok) return;
    setBulkBusy(true);
    try {
      for (const part of chunk(ids, 500)) await libraryApi.removeDocuments(part);
      push(interpolate(t.library.bulkTrashed, { length: ids.length }), "success");
      endSelection();
      void refreshKbs();
    } catch (e) {
      push(errorMessage(e, t.library.bulkTrashFailed), "error");
    } finally {
      setBulkBusy(false);
      void reload();
    }
  };

  const moveSelected = async (to: string | null) => {
    const ids = [...selected];
    setBulkBusy(true);
    try {
      for (const part of chunk(ids, 500)) await libraryApi.moveDocuments(part, to);
      const name = to ? (folders.find((f) => f.id === to)?.name ?? t.library.folder) : kbLabel(kb);
      push(interpolate(t.library.bulkMoved, { length: ids.length, name }), "success");
      endSelection();
    } catch (e) {
      push(errorMessage(e, t.library.moveFailed), "error");
    } finally {
      setBulkBusy(false);
      void reload();
    }
  };

  useEffect(() => {
    if (!selecting) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented || document.querySelector("[role=dialog]")) return;
      setSelecting(false);
      setSelected(new Set());
      setAnchor(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selecting]);

  // ── フォルダの操作 ───────────────────────────────────────────────────
  const createFolder = async () => {
    const name = creating?.trim();
    setCreating(null);
    if (!name || !kbId) return;
    try {
      const f = await libraryApi.createFolder(kbId, name, folderId);
      setFolders((all) => [...all, f]);
    } catch (e) {
      push(errorMessage(e, t.library.folderCreateFailed), "error");
    }
  };

  const removeFolder = async (f: FolderOut) => {
    const ok = await confirm({
      title: interpolate(t.library.folderTrashTitle, { name: f.name }),
      description: t.library.folderTrashBody,
      confirmLabel: t.library.trashConfirm,
      tone: "danger",
    });
    if (!ok) return;
    try {
      await libraryApi.removeFolder(f.id);
      push(interpolate(t.library.folderTrashed, { name: f.name }), "success");
      void refreshKbs();
      void reload();
    } catch (e) {
      push(errorMessage(e, t.library.deleteFailed), "error");
    }
  };

  const commitRename = async () => {
    if (!renaming) return;
    const { kind, id, value } = renaming;
    const name = value.trim();
    setRenaming(null);
    if (kind === "folder") {
      const before = folders.find((x) => x.id === id);
      if (!before || !name || name === before.name) return;
      setFolders((all) => all.map((x) => (x.id === id ? { ...x, name } : x)));
      try {
        await libraryApi.renameFolder(id, name);
      } catch (e) {
        setFolders((all) => all.map((x) => (x.id === id ? before : x)));
        push(errorMessage(e, t.library.renameFailed), "error");
      }
      return;
    }
    const before = docs?.find((x) => x.id === id);
    if (!before || !name || name === before.filename) return;
    setDocs((all) => all?.map((x) => (x.id === id ? { ...x, filename: name } : x)) ?? null);
    try {
      await libraryApi.rename(id, name);
    } catch (e) {
      setDocs((all) => all?.map((x) => (x.id === id ? before : x)) ?? null);
      push(errorMessage(e, t.library.renameFailed), "error");
    }
  };

  const subfolders = browsing ? childFolders(folders, folderId) : [];
  const crumbs = kbId ? breadcrumb(folders, folderId) : [];
  const here = crumbs.at(-1) ?? null;
  const busyCount = Object.entries(stats?.by_status ?? {})
    .filter(([s]) => docStatus(s).tone === "busy")
    .reduce((n, [, c]) => n + c, 0);
  const errorCount = (stats?.by_status.error ?? 0) + (stats?.by_status.cancelled ?? 0);
  const listEmpty = docs !== null && docs.length === 0 && subfolders.length === 0 && creating === null;

  // フォルダ行・パンくずを文書の移動先にする
  const dropTarget = (key: string, to: string | null) =>
    canEditFolders
      ? {
          onDragOver: (e: React.DragEvent) => {
            if (!e.dataTransfer.types.includes(DOC_MIME)) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
            setDropOn(key);
          },
          onDragLeave: () => setDropOn((k) => (k === key ? null : k)),
          onDrop: (e: React.DragEvent) => {
            const id = e.dataTransfer.getData(DOC_MIME);
            if (!id) return;
            e.preventDefault();
            e.stopPropagation();
            setDropOn(null);
            void moveDoc(id, to);
          },
        }
      : {};


  /** その行の名前を変えている最中なら、入力の受け渡し */
  const renameFor = (kind: "doc" | "folder", id: string): RenameState | null =>
    renaming?.kind === kind && renaming.id === id
      ? {
          value: renaming.value,
          onChange: (value) => setRenaming({ ...renaming, value }),
          onCommit: () => void commitRename(),
          onCancel: () => setRenaming(null),
        }
      : null;

  /** 文書の名前の下に出す置き場 */
  const locationOf = (d: DocumentOut) =>
    !kbId
      ? { text: kbNames.get(d.kb_id) ?? "", folder: false }
      : !browsing && d.folder_id
        ? { text: breadcrumb(folders, d.folder_id).map((x) => x.name).join(" / "), folder: true }
        : null;

  return (
    <main
      className="relative grid min-h-0 min-w-0 animate-fade-in grid-cols-[minmax(0,1fr)] grid-rows-[auto_auto_1fr] overflow-hidden bg-bg motion-reduce:animate-none"
      {...dropZone}
    >
      <DropOverlay visible={dragging && Boolean(target)} />
      <header className="sticky top-0 z-[5] flex h-[52px] items-center gap-2 border-b-[0.5px] border-divider bg-bg px-[18px] max-md:px-2.5">
        <IconButton
          label={t.common.openMenu}
          tooltip={false}
          icon="menu"
          iconSize={15}
          onClick={onOpenMenu}
          className="-ml-1 hidden h-[34px] w-[34px] text-fg max-md:inline-flex"
        />
        <nav aria-label={t.library.breadcrumbLabel} className="flex min-w-0 flex-1 items-center gap-0.5 text-body">
          {crumbs.length === 0 ? (
            <h1 className="m-0 truncate text-body font-semibold text-fg">{kbLabel(kb)}</h1>
          ) : (
            <>
              <button
                onClick={() => onOpenFolder(null)}
                {...dropTarget("crumb:root", null)}
                className={cn(
                  "min-w-0 shrink truncate rounded-control px-1.5 py-0.5 font-medium text-muted hover:bg-divider hover:text-fg max-md:max-w-[80px]",
                  dropOn === "crumb:root" && "bg-accent-soft text-accent",
                )}
              >
                {kbLabel(kb)}
              </button>
              {crumbs.map((f, i) => {
                const last = i === crumbs.length - 1;
                return (
                  <span key={f.id} className="flex min-w-0 items-center gap-0.5">
                    <Icon name="chevronRight" size={12} className="shrink-0 text-muted-2" />
                    {last ? (
                      <h1 className="m-0 truncate px-1.5 text-body font-semibold text-fg">{f.name}</h1>
                    ) : (
                      <button
                        onClick={() => onOpenFolder(f.id)}
                        {...dropTarget(`crumb:${f.id}`, f.id)}
                        className={cn(
                          "min-w-0 truncate rounded-control px-1.5 py-0.5 font-medium text-muted hover:bg-divider hover:text-fg max-md:hidden",
                          dropOn === `crumb:${f.id}` && "bg-accent-soft text-accent",
                        )}
                      >
                        {f.name}
                      </button>
                    )}
                  </span>
                );
              })}
            </>
          )}
          {/* 概要（題と件数）を出しているときは、同じ件数をここに重ねない */}
          {stats && crumbs.length === 0 && (search || filter !== "all" || selecting || stats.documents === 0) && (
            <span className="ml-2 shrink-0 font-mono text-caption text-muted max-md:hidden">
              {interpolate(t.library.statsLine, { documents: stats.documents.toLocaleString("ja-JP"), total_bytes: formatBytes(stats.total_bytes) })}
            </span>
          )}
          {kb && !kb.canWrite && (
            <Badge className="ml-2">{t.library.readOnly}</Badge>
          )}
        </nav>
        {docs && docs.length > 0 && (
          <button
            onClick={() => (selecting ? endSelection() : setSelecting(true))}
            aria-pressed={selecting}
            title={t.library.selectHint}
            className={cn(
              "inline-flex h-[30px] items-center gap-1.5 rounded-control border-[0.5px] px-2.5 text-footnote font-medium",
              selecting ? "border-accent bg-accent-soft text-accent" : "border-divider-strong text-fg hover:bg-divider",
            )}
          >
            <Icon name="check" size={13} />
            <span className="max-md:hidden">{selecting ? t.library.selectEnd : t.library.select}</span>
          </button>
        )}
        {kb && kb.kind === "org" && <KbShareButton kbId={kb.id} kbName={kb.name} />}
        <Button variant="secondary" size="sm"
          onClick={() => onAsk(kbId)}
          title={kb ? t.library.askKb : t.library.ask}
        >
          <Icon name="chat" size={13} />
          <span className="max-lg:hidden">{kb ? t.library.askKb : t.library.ask}</span>
        </Button>
        {canEditFolders && (
          <Button variant="secondary" size="sm"
            onClick={() => {
              setQuery("");
              setSearch("");
              setFilter("all");
              setCreating("");
            }}
            title={t.library.newFolder}
          >
            <Icon name="folder" size={13} />
            <span className="max-md:hidden">{t.library.folder}</span>
          </Button>
        )}
        {target && (
          <Menu open={addMenu} onOpenChange={setAddMenu}>
            <MenuTrigger asChild>
              <Button variant="primary" size="sm">
                <Icon name="plus" size={13} />
                {t.library.add}
                <Icon name="chevronDown" size={11} />
              </Button>
            </MenuTrigger>
            <MenuContent align="end">
              <MenuItem icon="doc" onSelect={() => fileRef.current?.click()}>
                {t.library.pickFiles}
              </MenuItem>
              <MenuItem icon="folder" hint={t.library.pickFolderHint} onSelect={() => dirRef.current?.click()}>
                {t.library.pickFolder}
              </MenuItem>
            </MenuContent>
          </Menu>
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
        <input
          ref={dirRef}
          type="file"
          hidden
          {...{ webkitdirectory: "" }}
          onChange={(e) => {
            const rel = [...(e.target.files ?? [])].map((file) => ({ file, path: file.webkitRelativePath || file.name }));
            e.target.value = "";
            void startFolderUpload(rel);
          }}
        />
      </header>

      <div className="flex flex-wrap items-center gap-2 border-b-[0.5px] border-divider px-[18px] py-2.5 max-md:px-3">
        <SearchField
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onClear={() => setQuery("")}
          placeholder={t.library.searchPlaceholder}
          className="min-w-[200px] flex-1 max-md:min-w-0"
        />
        <Segmented
          label={t.library.filterLabel}
          size="md"
          value={filter}
          onChange={setFilter}
          className="shrink-0"
          options={(
            [
              ["all", t.library.filterAll, null],
              ["busy", t.library.filterBusy, busyCount],
              ["error", t.library.filterError, errorCount],
            ] as const
          ).map(([key, label, n]) => [
            key,
            <>
              {label}
              {n ? <span className={cn("font-mono text-mini", key === "error" ? "text-danger" : "text-accent")}>{n}</span> : null}
            </>,
          ] as const)}
        />
      </div>


      <div className="min-h-0 overflow-y-auto">
        <DocumentsUploadQueue files={queue.files} onRemove={queue.remove} onRetry={queue.retry} onClear={queue.clear} />

        {docs === null ? (
          <ListSkeleton />
        ) : listEmpty && !search && filter === "all" && !folderId ? (
          <EmptyLibrary canUpload={Boolean(target)} onPick={() => fileRef.current?.click()} />
        ) : (
          <div className={cn("mx-auto max-w-[1100px] px-[18px] pb-10 pt-2 max-md:px-2", selecting && "pb-24")}>
            {crumbs.length === 0 && !search && filter === "all" && !selecting && (
              <LibraryOverview
                kbId={kbId}
                title={kbLabel(kb)}
                refreshKey={stats ? `${stats.documents}:${JSON.stringify(stats.by_status)}` : ""}
                onOpenDocument={onOpenDocument}
                onShowFailed={() => setFilter("error")}
              />
            )}
            <ListHeader />
            {!browsing && kbId && (search || filter !== "all") && (
              <div className="px-2 pb-1 pt-2 text-caption text-muted">{interpolate(t.library.searchingWhole, { kb: kbLabel(kb) })}</div>
            )}

            {creating !== null && (
              <NewFolderRow
                rename={{
                  value: creating,
                  placeholder: t.library.folderName,
                  onChange: setCreating,
                  onCommit: () => void createFolder(),
                  onCancel: () => setCreating(null),
                }}
              />
            )}

            {subfolders.map((f) => (
              <FolderRow
                key={f.id}
                folder={f}
                rename={renameFor("folder", f.id)}
                canEdit={canEditFolders}
                menuOpen={menuFor === f.id}
                onMenuToggle={(o) => setMenuFor(o ? f.id : null)}
                dropProps={dropTarget(`folder:${f.id}`, f.id)}
                dropActive={dropOn === `folder:${f.id}`}
                onOpen={() => onOpenFolder(f.id)}
                onStartRename={() => setRenaming({ kind: "folder", id: f.id, value: f.name })}
                onRemove={() => void removeFolder(f)}
              />
            ))}

            {listEmpty && (
              <div className="py-10 text-center text-body text-muted">
                {browsing ? (
                  <>
                    {t.library.folderEmpty}
                    {target && (
                      <span className="mt-1 block text-footnote text-muted-2">
                        {interpolate(t.library.folderDropHint, { name: here?.name ?? "" })}
                      </span>
                    )}
                  </>
                ) : (
                  t.library.noMatch
                )}
              </div>
            )}

            {docs.map((d) => (
              <DocumentRow
                key={d.id}
                doc={d}
                location={locationOf(d)}
                selecting={selecting}
                checked={selected.has(d.id)}
                movable={d.writable && canEditFolders}
                rename={renameFor("doc", d.id)}
                menuOpen={menuFor === d.id}
                onMenuToggle={(o) => setMenuFor(o ? d.id : null)}
                onPick={(shift) => pickRow(d.id, shift)}
                onOpen={() => onOpenDocument(d)}
                onRetry={() => void retry(d)}
                onStartRename={() => setRenaming({ kind: "doc", id: d.id, value: d.filename })}
                onMove={() => setMoving(d)}
                onRemove={() => void removeDoc(d)}
              />
            ))}
            {cursor && (
              <div className="pt-4 text-center">
                <Button variant="secondary" size="md" className="px-4" onClick={() => void loadMore()} disabled={loadingMore}>
                  {loadingMore ? t.common.loading : t.library.loadMore}
                </Button>
              </div>
            )}
          </div>
        )}
      </div>
      {moving && (
        <MoveDialog
          title={interpolate(t.library.moveTitleOne, { filename: moving.filename })}
          folders={folders}
          current={moving.folder_id}
          rootLabel={kbLabel(kb)}
          onCancel={() => setMoving(null)}
          onPick={(to) => {
            const id = moving.id;
            setMoving(null);
            void moveDoc(id, to);
          }}
        />
      )}
      {selecting && docs && (
        <BulkBar
          count={selected.size}
          total={docs.length}
          busy={bulkBusy}
          canMove={Boolean(kbId) && canEditFolders && [...selected].every((id) => docs.find((x) => x.id === id)?.writable)}
          canRemove={selected.size > 0 && [...selected].every((id) => docs.find((x) => x.id === id)?.writable)}
          onSelectAll={() => setSelected(new Set(docs.map((x) => x.id)))}
          onMove={() => setBulkMoving(true)}
          onRemove={() => void removeSelected()}
          onClear={endSelection}
        />
      )}
      {bulkMoving && (
        <MoveDialog
          title={interpolate(t.library.moveTitleMany, { size: selected.size })}
          folders={folders}
          current={browsing ? folderId : undefined}
          rootLabel={kbLabel(kb)}
          onCancel={() => setBulkMoving(false)}
          onPick={(to) => {
            setBulkMoving(false);
            void moveSelected(to);
          }}
        />
      )}
      {dialog}
    </main>
  );
}
