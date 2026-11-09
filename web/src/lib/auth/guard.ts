/** 画面のアクセス制御（specs/006-auth R12）。Cookie の有無だけで判断する楽観チェック。
 * 本当の検証は中継（セッション → JWT）と Python が行う。 */

const PUBLIC_PATHS = new Set(["/login", "/reset-password"]);

/** ログイン後に戻る先。自サイト内のパス以外は "/"。 */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return "/";
  return next;
}

/** 移動先（不要なら null）。 */
export function authRedirect(pathname: string, search: string, hasSession: boolean): string | null {
  const isPublic = PUBLIC_PATHS.has(pathname);
  if (hasSession) {
    if (pathname !== "/login") return null;
    return safeNext(new URLSearchParams(search).get("next"));
  }
  if (isPublic) return null;
  const back = pathname + search;
  return back === "/" ? "/login" : `/login?next=${encodeURIComponent(back)}`;
}
