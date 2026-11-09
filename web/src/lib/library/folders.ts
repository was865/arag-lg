/** フォルダの木（GET /v1/kbs/{kb}/folders は平らな一覧で返る）を画面向けに組み立てる。 */
export interface FolderLike {
  id: string;
  name: string;
  parent_id: string | null;
}

const byName = (a: FolderLike, b: FolderLike) => a.name.localeCompare(b.name, "ja");

/** 直下のフォルダ（名前順）。parentId = null ならルート直下。 */
export function childFolders<T extends FolderLike>(all: T[], parentId: string | null): T[] {
  return all.filter((f) => f.parent_id === parentId).sort(byName);
}

/** ルートから id までのフォルダ（id 自身を含む）。見つからなければ空。 */
export function breadcrumb<T extends FolderLike>(all: T[], id: string | null): T[] {
  const byId = new Map(all.map((f) => [f.id, f]));
  const path: T[] = [];
  const seen = new Set<string>();
  let cur = id ? byId.get(id) : undefined;
  while (cur && !seen.has(cur.id)) {
    seen.add(cur.id);
    path.unshift(cur);
    cur = cur.parent_id ? byId.get(cur.parent_id) : undefined;
  }
  return path;
}

/** 移動先の候補: 木を深さ優先・名前順で平らにする。 */
export function folderOptions<T extends FolderLike>(all: T[]): (T & { depth: number })[] {
  const out: (T & { depth: number })[] = [];
  const seen = new Set<string>();
  const walk = (parent: string | null, depth: number) => {
    for (const f of childFolders(all, parent)) {
      if (seen.has(f.id)) continue;
      seen.add(f.id);
      out.push({ ...f, depth });
      walk(f.id, depth + 1);
    }
  };
  walk(null, 0);
  return out;
}
