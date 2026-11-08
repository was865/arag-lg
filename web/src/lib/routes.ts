/** 画面の URL（チャット・文書ライブラリ・ごみ箱）。1 つの ChatApp が pushState で切り替える。 */
export type Route =
  | { view: "chat"; threadId: string | null }
  | { view: "library"; kbId: string | null }
  | { view: "trash" };

export function parseRoute(pathname: string): Route {
  const thread = pathname.match(/^\/c\/([^/]+)/);
  if (thread) return { view: "chat", threadId: decodeURIComponent(thread[1]) };
  const lib = pathname.match(/^\/library(?:\/([^/]+))?\/?$/);
  if (lib) return { view: "library", kbId: lib[1] ? decodeURIComponent(lib[1]) : null };
  if (/^\/trash\/?$/.test(pathname)) return { view: "trash" };
  return { view: "chat", threadId: null };
}

export function routePath(r: Route): string {
  if (r.view === "library") return r.kbId ? `/library/${encodeURIComponent(r.kbId)}` : "/library";
  if (r.view === "trash") return "/trash";
  return r.threadId ? `/c/${encodeURIComponent(r.threadId)}` : "/";
}
