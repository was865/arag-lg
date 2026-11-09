/** フォルダを構成ごとアップロードする（相対パス → フォルダの作成・振り分け）。 */
import { ACCEPTED_FILE_TYPES } from "@/lib/constants";

const ACCEPTED = new Set(ACCEPTED_FILE_TYPES.split(",").map((e) => e.trim().toLowerCase()));

export function isAccepted(name: string): boolean {
  const i = name.lastIndexOf(".");
  return i > 0 && ACCEPTED.has(name.slice(i).toLowerCase());
}

/** "A/B/x.pdf" → ["A", "B"]。隠しファイル・隠しフォルダ（. で始まる）は null。 */
export function splitRelPath(path: string): string[] | null {
  const parts = path.split("/").filter((p) => p && p !== "." && p !== "..");
  if (parts.some((p) => p.startsWith("."))) return null;
  return parts.slice(0, -1);
}

export const dirKey = (dir: string[]) => dir.join("/");

/** 作る必要のあるフォルダ（途中も含む）を、浅いものから順に一度ずつ。 */
export function planDirs(dirs: string[][]): string[][] {
  const seen = new Map<string, string[]>();
  for (const d of dirs) {
    for (let i = 1; i <= d.length; i++) {
      const p = d.slice(0, i);
      seen.set(dirKey(p), p);
    }
  }
  return [...seen.values()].sort((a, b) => a.length - b.length);
}

interface FolderLike {
  id: string;
  name: string;
  parent_id?: string | null;
}

/** 相対フォルダ → フォルダ id。既存の同名フォルダ（同じ親）があれば使い、無ければ create で作る。 */
export async function resolveFolders(
  base: string | null,
  dirs: string[][],
  existing: FolderLike[],
  create: (name: string, parentId: string | null) => Promise<string>,
): Promise<Map<string, string | null>> {
  const map = new Map<string, string | null>([["", base]]);
  const byParent = new Map<string, string>();
  for (const f of existing) byParent.set(`${f.parent_id ?? ""}\u0000${f.name}`, f.id);
  for (const d of planDirs(dirs)) {
    const parent = map.get(dirKey(d.slice(0, -1))) ?? null;
    const name = d[d.length - 1];
    const hit = byParent.get(`${parent ?? ""}\u0000${name}`);
    const id = hit ?? (await create(name, parent));
    byParent.set(`${parent ?? ""}\u0000${name}`, id);
    map.set(dirKey(d), id);
  }
  return map;
}

export interface RelFile {
  file: File;
  path: string;
}

/** ドロップされた項目からファイルと相対パスを集める（フォルダは中まで辿る）。 */
export async function readDropped(items: DataTransferItemList): Promise<RelFile[] | null> {
  const entries = [...items]
    .map((it) => (it.kind === "file" ? it.webkitGetAsEntry?.() : null))
    .filter((e): e is FileSystemEntry => !!e);
  if (!entries.some((e) => e.isDirectory)) return null; // ファイルだけなら従来どおり
  const out: RelFile[] = [];
  const walk = async (entry: FileSystemEntry, prefix: string): Promise<void> => {
    if (entry.isFile) {
      const file = await new Promise<File>((ok, ng) => (entry as FileSystemFileEntry).file(ok, ng));
      out.push({ file, path: prefix + entry.name });
      return;
    }
    const reader = (entry as FileSystemDirectoryEntry).createReader();
    // readEntries は 1 回で全部返さないので空になるまで読む
    for (;;) {
      const batch = await new Promise<FileSystemEntry[]>((ok, ng) => reader.readEntries(ok, ng));
      if (!batch.length) break;
      for (const child of batch) await walk(child, `${prefix}${entry.name}/`);
    }
  };
  for (const e of entries) await walk(e, "");
  return out;
}
