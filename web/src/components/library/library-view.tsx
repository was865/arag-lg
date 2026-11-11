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
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Icon, type IconName } from "@/components/icons";
import { DocumentsUploadQueue, DropOverlay } from "@/components/uploads/uploads";
import { useToast } from "@/components/feedback/toast-provider";
import { MoveDialog } from "@/components/library/move-dialog";
import { useConfirm } from "@/hooks/use-confirm";
import { refreshKbs, useKbs } from "@/hooks/use-kbs";
import { useUploadQueue } from "@/hooks/use-upload-queue";
import {
  dirKey,
  isAccepted,
  readDropped,
  resolveFolders,
  splitRelPath,
  type RelFile,
} from "@/lib/library/folder-upload";
import { ApiError } from "@/lib/chat/api";
import { ACCEPTED_FILE_TYPES } from "@/lib/constants";
import { getFileMeta } from "@/lib/file-types";
import { libraryApi, originalUrl, type DocumentOut, type FolderOut } from "@/lib/library/api";
import { LibraryOverview } from "@/components/library/library-overview";
import { KbShareButton } from "@/components/access/kb-share-button";
import { chunk, selectRange, toggleId } from "@/lib/library/selection";
import { breadcrumb, childFolders } from "@/lib/library/folders";
import {
  docStatus,
  filterStatuses,
  formatBytes,
  formatDate,
  kbLabel,
  uploadTarget,
  type StatusFilter,
  type StatusTone,
} from "@/lib/library/view";
import { cn } from "@/lib/utils";

const PAGE = 100;
/** ライブラリ内のドラッグ（文書の移動）。OS からのファイルのドロップと区別する。 */
const DOC_MIME = "application/x-arag-document";

const TONE: Record<StatusTone, string> = {
  ok: "text-muted",
  busy: "text-accent",
  danger: "text-danger",
  muted: "text-muted-2",
};

const ROW_GRID =
  "grid grid-cols-[minmax(0,1fr)_120px_70px_80px_64px_32px] items-center gap-3 max-md:grid-cols-[minmax(0,1fr)_32px] max-md:gap-2";

type Stats = { documents: number; total_bytes: number; by_status: Record<string, number> };

const errorMessage = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

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

  const [docs, setDocs] = useState<DocumentOut[] | null>(null);
  const [folders, setFolders] = useState<FolderOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [stats, setStats] = useState<Stats | null>(null);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [renaming, setRenaming] = useState<{ kind: "doc" | "folder"; id: string; value: string } | null>(null);
  const [creating, setCreating] = useState<string | null>(null);
  const [moving, setMoving] = useState<DocumentOut | null>(null);
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
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
  const dragDepth = useRef(0);

  // 名前の絞り込みは入力が落ち着いてからサーバーに問い合わせる（全件が対象）
  useEffect(() => {
    const t = window.setTimeout(() => setSearch(query.trim()), 250);
    return () => window.clearTimeout(t);
  }, [query]);

  // フォルダをたどるのは KB を開いていて、絞り込んでいないときだけ
  const browsing = Boolean(kbId) && !search && filter === "all";
  const listQuery = useMemo(
    () => ({
      kbId,
      folderId: browsing ? folderId : undefined,
      status: filterStatuses(filter),
      q: search,
      limit: PAGE,
    }),
    [kbId, folderId, browsing, filter, search],
  );

  const reload = useCallback(async () => {
    try {
      const [page, st, fs] = await Promise.all([
        libraryApi.documents(listQuery),
        libraryApi.stats(kbId),
        kbId ? libraryApi.folders(kbId) : Promise.resolve([]),
      ]);
      setDocs(page.items);
      setCursor(page.next_cursor);
      setStats(st);
      setFolders(fs);
    } catch (e) {
      setDocs((d) => d ?? []);
      push(errorMessage(e, "文書の一覧を取得できませんでした"), "error");
    }
  }, [kbId, listQuery, push]);

  // KB を切り替えたら絞り込みを戻し、フォルダを移ったら前の一覧は見せない
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
      setStats(null);
      setFolders([]);
      setQuery("");
      setSearch("");
      setFilter("all");
    }
    setShownKb(kbId);
    setShownFolder(folderId);
    setDocs(null);
    setCursor(null);
    setCreating(null);
    setRenaming(null);
  }
  useEffect(() => {
    // 取得は非同期で、結果は then の中で反映する
    let alive = true;
    Promise.all([
      libraryApi.documents(listQuery),
      libraryApi.stats(kbId),
      kbId ? libraryApi.folders(kbId) : Promise.resolve([]),
    ])
      .then(([page, st, fs]) => {
        if (!alive) return;
        setDocs(page.items);
        setCursor(page.next_cursor);
        setStats(st);
        setFolders(fs);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setDocs([]);
        push(errorMessage(e, "文書の一覧を取得できませんでした"), "error");
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
    // 開いている KB に送るときだけ、開いているフォルダへ入れる
    queue.add(target.id, files, target.id === kbId ? folderId : null);
    // 送信直後の「待機中」を一覧にも出す
    window.setTimeout(() => void reload(), 1200);
  };

  /** フォルダを構成ごと送る（同名のフォルダがあれば中に入れ、無ければ作る）。 */
  const startFolderUpload = async (rel: RelFile[]) => {
    if (!target) {
      push("このナレッジベースには追加できません（閲覧のみ）", "error");
      return;
    }
    const groups = new Map<string, { dir: string[]; files: File[] }>();
    let skipped = 0;
    for (const r of rel) {
      const dir = splitRelPath(r.path);
      if (dir === null || !isAccepted(r.file.name)) {
        skipped += 1;
        continue;
      }
      const g = groups.get(dirKey(dir)) ?? { dir, files: [] };
      g.files.push(r.file);
      groups.set(dirKey(dir), g);
    }
    const total = [...groups.values()].reduce((n, g) => n + g.files.length, 0);
    if (!total) {
      push("追加できる形式のファイルがありませんでした", "error");
      return;
    }
    const base = target.id === kbId ? folderId : null;
    try {
      const existing = await libraryApi.folders(target.id);
      const map = await resolveFolders(
        base,
        [...groups.values()].map((g) => g.dir),
        existing,
        async (name, parent) => (await libraryApi.createFolder(target.id, name, parent)).id,
      );
      for (const [key, g] of groups) queue.add(target.id, g.files, map.get(key) ?? null);
    } catch (e) {
      push(errorMessage(e, "フォルダを作成できませんでした"), "error");
      void reload();
      return;
    }
    push(
      skipped
        ? `${total} 件のファイルをフォルダごと追加しています（対象外の ${skipped} 件は除きました）`
        : `${total} 件のファイルをフォルダごと追加しています`,
      "success",
    );
    void reload();
    window.setTimeout(() => void reload(), 1200);
  };

  // ── 文書の操作 ─────────────────────────────────────────────────────
  const removeDoc = async (d: DocumentOut) => {
    setDocs((all) => all?.filter((x) => x.id !== d.id) ?? null);
    try {
      await libraryApi.remove(d.id);
      push(`「${d.filename}」をごみ箱に移しました`, "success");
      void refreshKbs();
      void reload();
    } catch (e) {
      void reload();
      push(errorMessage(e, "削除できませんでした"), "error");
    }
  };

  const moveDoc = async (docId: string, to: string | null) => {
    const d = docs?.find((x) => x.id === docId);
    if (!d || d.folder_id === to) return;
    // いまの一覧（このフォルダ）から外れるなら先に消す
    if (browsing) setDocs((all) => all?.filter((x) => x.id !== docId) ?? null);
    try {
      await libraryApi.moveDocuments([docId], to);
      const name = to ? (folders.find((f) => f.id === to)?.name ?? "フォルダ") : kbLabel(kb);
      push(`「${d.filename}」を「${name}」に移しました`, "success");
    } catch (e) {
      push(errorMessage(e, "移動できませんでした"), "error");
    }
    void reload();
  };

  const retry = async (d: DocumentOut) => {
    if (!d.job_id) return;
    try {
      await libraryApi.retryJob(d.job_id);
      push(`「${d.filename}」を解析し直します`, "info");
      void reload();
    } catch (e) {
      push(errorMessage(e, "再実行できませんでした"), "error");
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
      title: `${ids.length} 件の文書をごみ箱に移しますか？`,
      description: "検索の対象から外れます。ごみ箱から元に戻せます。",
      confirmLabel: "ごみ箱に移す",
      tone: "danger",
    });
    if (!ok) return;
    setBulkBusy(true);
    try {
      for (const part of chunk(ids, 500)) await libraryApi.removeDocuments(part);
      push(`${ids.length} 件をごみ箱に移しました`, "success");
      endSelection();
      void refreshKbs();
    } catch (e) {
      push(errorMessage(e, "ごみ箱に移せませんでした"), "error");
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
      const name = to ? (folders.find((f) => f.id === to)?.name ?? "フォルダ") : kbLabel(kb);
      push(`${ids.length} 件を「${name}」に移しました`, "success");
      endSelection();
    } catch (e) {
      push(errorMessage(e, "移動できませんでした"), "error");
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
      push(errorMessage(e, "フォルダを作成できませんでした"), "error");
    }
  };

  const removeFolder = async (f: FolderOut) => {
    const ok = await confirm({
      title: `フォルダ「${f.name}」をごみ箱に移しますか？`,
      description: "中のフォルダと文書もまとめて移ります。ごみ箱から元に戻せます。",
      confirmLabel: "ごみ箱に移す",
      tone: "danger",
    });
    if (!ok) return;
    try {
      await libraryApi.removeFolder(f.id);
      push(`フォルダ「${f.name}」をごみ箱に移しました`, "success");
      void refreshKbs();
      void reload();
    } catch (e) {
      push(errorMessage(e, "削除できませんでした"), "error");
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
        push(errorMessage(e, "名前を変更できませんでした"), "error");
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
      push(errorMessage(e, "名前を変更できませんでした"), "error");
    }
  };

  // 処理中の文書がある間は一覧を時々取り直す（キュー外＝別の人や以前のアップロード分も追う）
  const hasBusy = docs?.some((d) => docStatus(d.status).tone === "busy") ?? false;
  useEffect(() => {
    if (!hasBusy) return;
    const t = window.setInterval(() => void reload(), 5000);
    return () => window.clearInterval(t);
  }, [hasBusy, reload]);

  const subfolders = browsing ? childFolders(folders, folderId) : [];
  const crumbs = kbId ? breadcrumb(folders, folderId) : [];
  const here = crumbs.at(-1) ?? null;
  const busyCount = Object.entries(stats?.by_status ?? {})
    .filter(([s]) => docStatus(s).tone === "busy")
    .reduce((n, [, c]) => n + c, 0);
  const errorCount = (stats?.by_status.error ?? 0) + (stats?.by_status.cancelled ?? 0);
  const listEmpty = docs !== null && docs.length === 0 && subfolders.length === 0 && creating === null;

  // 画面全体を OS からのファイルのドロップ先にする
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
      if (!e.dataTransfer.types.includes("Files")) return;
      e.preventDefault();
      dragDepth.current = 0;
      setDragging(false);
      // フォルダが含まれていれば構成ごと送る（エントリはイベント中に取り出す）
      const files = [...e.dataTransfer.files];
      void readDropped(e.dataTransfer.items).then(
        (rel) => (rel ? void startFolderUpload(rel) : startUpload(files)),
        () => startUpload(files),
      );
    },
  };

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

  return (
    <main
      className="relative grid min-h-0 min-w-0 grid-cols-[minmax(0,1fr)] grid-rows-[auto_auto_1fr] overflow-hidden bg-bg"
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
        <nav aria-label="場所" className="flex min-w-0 flex-1 items-center gap-0.5 text-[13.5px]">
          {crumbs.length === 0 ? (
            <h1 className="m-0 truncate text-[13.5px] font-semibold text-fg">{kbLabel(kb)}</h1>
          ) : (
            <>
              <button
                onClick={() => onOpenFolder(null)}
                {...dropTarget("crumb:root", null)}
                className={cn(
                  "min-w-0 shrink truncate rounded-md px-1.5 py-0.5 font-medium text-muted hover:bg-divider hover:text-fg max-md:max-w-[80px]",
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
                      <h1 className="m-0 truncate px-1.5 text-[13.5px] font-semibold text-fg">{f.name}</h1>
                    ) : (
                      <button
                        onClick={() => onOpenFolder(f.id)}
                        {...dropTarget(`crumb:${f.id}`, f.id)}
                        className={cn(
                          "min-w-0 truncate rounded-md px-1.5 py-0.5 font-medium text-muted hover:bg-divider hover:text-fg max-md:hidden",
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
          {stats && crumbs.length === 0 && (
            <span className="ml-2 shrink-0 font-mono text-[11px] text-muted max-md:hidden">
              {stats.documents.toLocaleString("ja-JP")} 件 · {formatBytes(stats.total_bytes)}
            </span>
          )}
          {kb && !kb.canWrite && (
            <span className="ml-2 shrink-0 rounded-full border-[0.5px] border-divider-strong px-1.5 py-px text-[10px] font-semibold text-muted">
              閲覧のみ
            </span>
          )}
        </nav>
        {docs && docs.length > 0 && (
          <button
            onClick={() => (selecting ? endSelection() : setSelecting(true))}
            aria-pressed={selecting}
            title="複数の文書を選ぶ"
            className={cn(
              "inline-flex h-[30px] items-center gap-1.5 rounded-lg border-[0.5px] px-2.5 text-[12px] font-medium",
              selecting ? "border-accent bg-accent-soft text-accent" : "border-divider-strong text-fg hover:bg-divider",
            )}
          >
            <Icon name="check" size={13} />
            <span className="max-md:hidden">{selecting ? "選択をやめる" : "選択"}</span>
          </button>
        )}
        {kb && kb.kind === "org" && <KbShareButton kbId={kb.id} kbName={kb.name} />}
        <Button variant="secondary" size="sm"
          onClick={() => onAsk(kbId)}
          title={kb ? "このナレッジベースに質問" : "質問する"}
        >
          <Icon name="chat" size={13} />
          <span className="max-lg:hidden">{kb ? "このナレッジベースに質問" : "質問する"}</span>
        </Button>
        {canEditFolders && (
          <Button variant="secondary" size="sm"
            onClick={() => {
              setQuery("");
              setSearch("");
              setFilter("all");
              setCreating("");
            }}
            title="新しいフォルダ"
          >
            <Icon name="folder" size={13} />
            <span className="max-md:hidden">フォルダ</span>
          </Button>
        )}
        {target && (
          <span className="relative">
            <Button variant="primary" size="sm"
              onClick={() => setAddMenu((x) => !x)}
              aria-haspopup="menu"
              aria-expanded={addMenu}
            >
              <Icon name="plus" size={13} />
              追加
              <Icon name="chevronDown" size={11} />
            </Button>
            {addMenu && (
              <>
                <div className="fixed inset-0 z-20" onClick={() => setAddMenu(false)} />
                <div
                  role="menu"
                  className="absolute right-0 top-9 z-30 w-[200px] animate-pop-in overflow-hidden rounded-[10px] border-[0.5px] border-divider-strong bg-surface p-1 shadow-e2"
                >
                  {(
                    [
                      ["doc", "ファイルを選ぶ", ""],
                      ["folder", "フォルダを選ぶ", "中のフォルダ構成も再現します"],
                    ] as const
                  ).map(([icon, label, hint]) => (
                    <button
                      key={label}
                      role="menuitem"
                      onClick={() => {
                        setAddMenu(false);
                        (icon === "folder" ? dirRef : fileRef).current?.click();
                      }}
                      className="flex w-full items-start gap-2 rounded-md px-2.5 py-1.5 text-left text-[12.5px] font-medium text-fg hover:bg-divider"
                    >
                      <span className="mt-[2px]">
                        <Icon name={icon} size={13} />
                      </span>
                      <span>
                        {label}
                        {hint && <span className="block text-[11px] font-normal text-muted">{hint}</span>}
                      </span>
                    </button>
                  ))}
                </div>
              </>
            )}
          </span>
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
        <label className="flex h-8 min-w-[200px] flex-1 items-center gap-2 rounded-lg border-[0.5px] border-divider-strong bg-surface px-2.5 text-muted focus-within:border-accent max-md:min-w-0">
          <Icon name="search" size={13} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="文書名で探す"
            className="min-w-0 flex-1 border-0 bg-transparent text-[13px] text-fg outline-none placeholder:text-muted-2"
          />
          {query && (
            <button onClick={() => setQuery("")} aria-label="検索語を消す" className="text-muted hover:text-fg">
              <Icon name="close" size={12} />
            </button>
          )}
        </label>
        <div role="tablist" className="flex shrink-0 rounded-lg bg-surface-2 p-0.5">
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
                filter === key ? "bg-surface text-fg shadow-e1" : "text-muted hover:text-fg",
              )}
            >
              {label}
              {n ? (
                <span className={cn("font-mono text-[10.5px]", key === "error" ? "text-danger" : "text-accent")}>
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
        ) : listEmpty && !search && filter === "all" && !folderId ? (
          <EmptyLibrary canUpload={Boolean(target)} onPick={() => fileRef.current?.click()} />
        ) : (
          <div className={cn("mx-auto max-w-[1100px] px-[18px] pb-10 pt-2 max-md:px-2", selecting && "pb-24")}>
            {crumbs.length === 0 && !search && filter === "all" && !selecting && (
              <LibraryOverview
                kbId={kbId}
                refreshKey={stats ? `${stats.documents}:${JSON.stringify(stats.by_status)}` : ""}
                onOpenDocument={onOpenDocument}
                onShowFailed={() => setFilter("error")}
              />
            )}
            <div
              className={cn(
                ROW_GRID,
                "border-b-[0.5px] border-divider px-2 py-2 text-[10.5px] font-semibold uppercase tracking-[0.05em] text-muted-2 max-md:hidden",
              )}
            >
              <span>名前</span>
              <span>状態</span>
              <span className="text-right">ページ</span>
              <span className="text-right">サイズ</span>
              <span className="text-right">追加日</span>
              <span />
            </div>
            {!browsing && kbId && (search || filter !== "all") && (
              <div className="px-2 pb-1 pt-2 text-[11.5px] text-muted">
                {kbLabel(kb)} 全体から探しています
              </div>
            )}

            {creating !== null && (
              <div className={cn(ROW_GRID, "rounded-lg px-2 py-2")}>
                <div className="flex min-w-0 items-center gap-2.5">
                  <FolderIcon />
                  <input
                    autoFocus
                    value={creating}
                    placeholder="フォルダ名"
                    onChange={(e) => setCreating(e.target.value)}
                    onBlur={() => void createFolder()}
                    onKeyDown={(e) => {
                      if (e.nativeEvent.isComposing) return;
                      if (e.key === "Enter") void createFolder();
                      if (e.key === "Escape") setCreating(null);
                    }}
                    className="w-full max-w-[360px] rounded-md border-[0.5px] border-accent bg-surface px-1.5 py-0.5 text-[13px] text-fg outline-none"
                  />
                </div>
              </div>
            )}

            {subfolders.map((f) => (
              <div
                key={f.id}
                {...dropTarget(`folder:${f.id}`, f.id)}
                className={cn(
                  ROW_GRID,
                  "group/row rounded-lg px-2 py-2 hover:bg-surface-2",
                  dropOn === `folder:${f.id}` && "bg-accent-soft outline outline-1 outline-accent",
                )}
              >
                <div className="flex min-w-0 items-center gap-2.5">
                  <FolderIcon />
                  {renaming?.kind === "folder" && renaming.id === f.id ? (
                    <RenameInput
                      value={renaming.value}
                      onChange={(value) => setRenaming({ ...renaming, value })}
                      onCommit={() => void commitRename()}
                      onCancel={() => setRenaming(null)}
                    />
                  ) : (
                    <button
                      onClick={() => onOpenFolder(f.id)}
                      title={f.name}
                      className="min-w-0 flex-1 truncate text-left text-[13px] font-medium text-fg hover:text-accent"
                    >
                      {f.name}
                      <span className="ml-2 hidden font-normal text-muted max-md:inline">
                        {f.document_count} 件
                      </span>
                    </button>
                  )}
                </div>
                <span className="text-[12px] text-muted max-md:hidden">{f.document_count} 件</span>
                <span className="max-md:hidden" />
                <span className="max-md:hidden" />
                <span className="text-right font-mono text-[11.5px] text-muted max-md:hidden">
                  {formatDate(f.created_at)}
                </span>
                {canEditFolders ? (
                  <RowMenu
                    open={menuFor === f.id}
                    onToggle={(o) => setMenuFor(o ? f.id : null)}
                    items={[
                      { label: "開く", icon: "folder", onClick: () => onOpenFolder(f.id) },
                      {
                        label: "名前を変更",
                        icon: "pencil",
                        onClick: () => setRenaming({ kind: "folder", id: f.id, value: f.name }),
                      },
                      { label: "ごみ箱へ移動", icon: "trash", danger: true, onClick: () => void removeFolder(f) },
                    ]}
                  />
                ) : (
                  <span />
                )}
              </div>
            ))}

            {listEmpty && (
              <div className="py-10 text-center text-[13px] text-muted">
                {browsing ? (
                  <>
                    このフォルダは空です
                    {target && (
                      <span className="mt-1 block text-[12px] text-muted-2">
                        ファイルをドロップすると「{here?.name}」に追加します
                      </span>
                    )}
                  </>
                ) : (
                  "条件に合う文書はありません"
                )}
              </div>
            )}

            {docs.map((d) => {
              const meta = getFileMeta(d.filename);
              const st = docStatus(d.status);
              const busy = st.tone === "busy";
              const movable = d.writable && canEditFolders;
              const checked = selected.has(d.id);
              return (
                <div
                  key={d.id}
                  aria-selected={selecting ? checked : undefined}
                  onClick={(e) => {
                    if (!selecting) return;
                    if ((e.target as HTMLElement).closest("[data-row-menu]")) return;
                    e.preventDefault();
                    pickRow(d.id, e.shiftKey);
                  }}
                  draggable={!selecting && movable && renaming?.id !== d.id}
                  onDragStart={(e) => {
                    e.dataTransfer.setData(DOC_MIME, d.id);
                    e.dataTransfer.effectAllowed = "move";
                  }}
                  className={cn(
                    ROW_GRID,
                    "group/row rounded-lg px-2 py-2",
                    selecting && "cursor-pointer select-none",
                    checked ? "bg-accent-soft" : "hover:bg-surface-2",
                  )}
                >
                  <div className="flex min-w-0 items-center gap-2.5">
                    <button
                      type="button"
                      role="checkbox"
                      aria-checked={checked}
                      aria-label={`「${d.filename}」を選ぶ`}
                      onClick={(e) => {
                        e.stopPropagation();
                        pickRow(d.id, e.shiftKey);
                      }}
                      className="group/check relative grid h-8 w-8 shrink-0 place-items-center rounded-lg"
                      style={
                        selecting
                          ? undefined
                          : { color: meta.color, background: `color-mix(in srgb, ${meta.color} 12%, transparent)` }
                      }
                    >
                      {selecting ? (
                        <CheckBox checked={checked} />
                      ) : (
                        <>
                          <span className="group-hover/row:hidden max-md:!block">
                            <Icon name={meta.iconName} size={15} />
                          </span>
                          <span className="hidden group-hover/row:block max-md:!hidden">
                            <CheckBox checked={false} />
                          </span>
                        </>
                      )}
                    </button>
                    <div className="min-w-0 flex-1">
                      {renaming?.kind === "doc" && renaming.id === d.id ? (
                        <RenameInput
                          value={renaming.value}
                          onChange={(value) => setRenaming({ ...renaming, value })}
                          onCommit={() => void commitRename()}
                          onCancel={() => setRenaming(null)}
                        />
                      ) : (
                        <button
                          onClick={() => !selecting && onOpenDocument(d)}
                          title={d.filename}
                          className="block max-w-full truncate text-left text-[13px] font-medium text-fg hover:text-accent"
                        >
                          {d.filename}
                        </button>
                      )}
                      <div className="flex items-center gap-1.5 truncate text-[11px] text-muted">
                        {!kbId && <span className="truncate">{kbNames.get(d.kb_id) ?? ""}</span>}
                        {kbId && !browsing && d.folder_id && (
                          <span className="inline-flex min-w-0 items-center gap-1 truncate">
                            <Icon name="folder" size={10} />
                            {breadcrumb(folders, d.folder_id)
                              .map((x) => x.name)
                              .join(" / ")}
                          </span>
                        )}
                        <span className={cn("hidden max-md:inline", TONE[st.tone])}>
                          {(!kbId || (!browsing && d.folder_id)) && "· "}
                          {st.label}
                        </span>
                        <span className="hidden max-md:inline">· {formatDate(d.created_at)}</span>
                        {d.status === "ready" && d.chunk_count > 0 && (
                          <span className="max-md:hidden">
                            {(!kbId || (!browsing && d.folder_id)) && "· "}
                            {d.chunk_count.toLocaleString("ja-JP")} チャンク
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <span className={cn("inline-flex items-center gap-1.5 text-[12px] max-md:hidden", TONE[st.tone])}>
                    {busy && (
                      <span className="h-2.5 w-2.5 animate-spin-fast rounded-full border-[1.5px] border-divider-strong border-t-accent" />
                    )}
                    {st.tone === "ok" && <span className="h-1.5 w-1.5 rounded-full bg-[#3c9a5f]" />}
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
                        onClick: () => window.open(originalUrl(d.id), "_blank", "noopener"),
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
                              onClick: () => setRenaming({ kind: "doc", id: d.id, value: d.filename }),
                            },
                            ...(movable
                              ? [{ label: "移動…", icon: "folder" as const, onClick: () => setMoving(d) }]
                              : []),
                            {
                              label: "ごみ箱へ移動",
                              icon: "trash" as const,
                              danger: true,
                              onClick: () => void removeDoc(d),
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
      {moving && (
        <MoveDialog
          title={`「${moving.filename}」の移動先`}
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
          title={`${selected.size} 件の移動先`}
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

function FolderIcon() {
  return (
    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent">
      <Icon name="folder" size={15} />
    </span>
  );
}

function RenameInput({
  value,
  onChange,
  onCommit,
  onCancel,
}: {
  value: string;
  onChange: (v: string) => void;
  onCommit: () => void;
  onCancel: () => void;
}) {
  return (
    <input
      autoFocus
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onBlur={onCommit}
      onKeyDown={(e) => {
        if (e.nativeEvent.isComposing) return;
        if (e.key === "Enter") onCommit();
        if (e.key === "Escape") onCancel();
      }}
      className="w-full rounded-md border-[0.5px] border-accent bg-surface px-1.5 py-0.5 text-[13px] text-fg outline-none"
    />
  );
}

interface MenuItem {
  label: string;
  icon: IconName;
  onClick: () => void;
  danger?: boolean;
}

function RowMenu({ open, onToggle, items }: { open: boolean; onToggle: (open: boolean) => void; items: MenuItem[] }) {
  return (
    <span data-row-menu className="relative justify-self-end">
      <button
        aria-label="操作メニュー"
        onClick={() => onToggle(!open)}
        className={cn(
          "grid h-7 w-7 place-items-center rounded-md text-muted hover:bg-divider hover:text-fg",
          !open && "opacity-0 focus-visible:opacity-100 group-hover/row:opacity-100 max-md:opacity-100",
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
                  it.danger ? "text-danger hover:bg-danger-soft" : "text-fg hover:bg-divider",
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

function EmptyLibrary({ canUpload, onPick }: { canUpload: boolean; onPick: () => void }) {
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
          {canUpload ? "文書を追加して、質問に使いましょう" : "このナレッジベースにはまだ文書がありません"}
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

function CheckBox({ checked }: { checked: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        "grid h-[18px] w-[18px] place-items-center rounded-[5px] border-[1.5px]",
        checked ? "border-accent bg-accent text-white" : "border-divider-strong bg-surface text-transparent",
      )}
    >
      <Icon name="check" size={11} />
    </span>
  );
}

function BulkBar({
  count,
  total,
  busy,
  canMove,
  canRemove,
  onSelectAll,
  onMove,
  onRemove,
  onClear,
}: {
  count: number;
  total: number;
  busy: boolean;
  canMove: boolean;
  canRemove: boolean;
  onSelectAll: () => void;
  onMove: () => void;
  onRemove: () => void;
  onClear: () => void;
}) {
  const btn =
    "inline-flex h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg px-2.5 text-[12.5px] font-medium disabled:cursor-not-allowed disabled:opacity-45";
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[6] flex justify-center px-3 pb-[max(14px,env(safe-area-inset-bottom))]">
      <div
        role="toolbar"
        aria-label="選択した文書の操作"
        className="pointer-events-auto flex max-w-full animate-pop-in items-center gap-1 rounded-[14px] border-[0.5px] border-divider-strong bg-surface p-1.5 pl-3.5 shadow-e3"
      >
        <span className="mr-1 shrink-0 whitespace-nowrap text-[12.5px] font-semibold text-fg">
          {count} 件を選択
        </span>
        <button onClick={onSelectAll} disabled={busy || count === total} className={cn(btn, "text-fg-2 hover:bg-divider max-md:hidden")}>
          すべて選択
        </button>
        <button onClick={onMove} disabled={busy || count === 0 || !canMove} className={cn(btn, "text-fg hover:bg-divider")}>
          <Icon name="folder" size={13} />
          移動
        </button>
        <button onClick={onRemove} disabled={busy || !canRemove} className={cn(btn, "text-danger hover:bg-danger-soft")}>
          <Icon name="trash" size={13} />
          ごみ箱へ
        </button>
        <button onClick={onClear} aria-label="選択を解除" className={cn(btn, "w-8 justify-center px-0 text-muted hover:bg-divider hover:text-fg")}>
          <Icon name="close" size={13} />
        </button>
      </div>
    </div>
  );
}
