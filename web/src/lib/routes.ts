/** 画面の URL（チャット・文書ライブラリ・ごみ箱）。1 つの ChatApp が pushState で切り替える。 */
export type Route =
  | { view: "chat"; threadId: string | null }
  | { view: "library"; kbId: string | null; folderId?: string | null }
  | { view: "trash" };

export function parseRoute(pathname: string): Route {
  const thread = pathname.match(/^\/c\/([^/]+)/);
  if (thread) return { view: "chat", threadId: decodeURIComponent(thread[1]) };
  const lib = pathname.match(/^\/library(?:\/([^/]+)(?:\/([^/]+))?)?\/?$/);
  if (lib) {
    const kbId = lib[1] ? decodeURIComponent(lib[1]) : null;
    return lib[2] ? { view: "library", kbId, folderId: decodeURIComponent(lib[2]) } : { view: "library", kbId };
  }
  if (/^\/trash\/?$/.test(pathname)) return { view: "trash" };
  return { view: "chat", threadId: null };
}

export function routePath(r: Route): string {
  if (r.view === "library") {
    if (!r.kbId) return "/library";
    const kb = `/library/${encodeURIComponent(r.kbId)}`;
    return r.folderId ? `${kb}/${encodeURIComponent(r.folderId)}` : kb;
  }
  if (r.view === "trash") return "/trash";
  return r.threadId ? `/c/${encodeURIComponent(r.threadId)}` : "/";
}
