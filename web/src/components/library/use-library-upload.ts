"use client";

/** 文書ライブラリへの追加（ファイル・フォルダごと・画面へのドロップ）。送り先は開いている KB のフォルダ（「すべて」なら個人 KB）。 */
import { useRef, useState } from "react";
import { useToast } from "@/components/feedback/toast-provider";
import { errorMessage } from "@/components/library/use-library-list";
import { refreshKbs, type KbInfo } from "@/hooks/use-kbs";
import { useUploadQueue } from "@/hooks/use-upload-queue";
import { libraryApi } from "@/lib/library/api";
import { dirKey, isAccepted, readDropped, resolveFolders, splitRelPath, type RelFile } from "@/lib/library/folder-upload";

export function useLibraryUpload({
  target,
  kbId,
  folderId,
  reload,
}: {
  /** 送り先の KB（書けなければ null） */
  target: KbInfo | null;
  kbId: string | null;
  folderId: string | null;
  reload: () => Promise<void>;
}) {
  const push = useToast();
  const [dragging, setDragging] = useState(false);
  const dragDepth = useRef(0);
  const queue = useUploadQueue({
    onSettled: () => {
      void reload();
      void refreshKbs();
    },
  });

  const readOnly = () => push("このナレッジベースには追加できません（閲覧のみ）", "error");

  const startUpload = (list: FileList | File[] | null) => {
    const files = [...(list ?? [])];
    if (!files.length) return;
    if (!target) return readOnly();
    // 開いている KB に送るときだけ、開いているフォルダへ入れる
    queue.add(target.id, files, target.id === kbId ? folderId : null);
    // 送信直後の「待機中」を一覧にも出す
    window.setTimeout(() => void reload(), 1200);
  };

  /** フォルダを構成ごと送る（同名のフォルダがあれば中に入れ、無ければ作る）。 */
  const startFolderUpload = async (rel: RelFile[]) => {
    if (!target) return readOnly();
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

  /** 画面全体を OS からのファイルのドロップ先にする props */
  const dropZone = {
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

  return { queue, dragging, dropZone, startUpload, startFolderUpload };
}
