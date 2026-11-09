/** 未ログインの画面アクセスを /login へ（Next 16 の Proxy。旧 middleware）。specs/006-auth R12。 */
import { getSessionCookie } from "better-auth/cookies";
import { NextResponse, type NextRequest } from "next/server";
import { authRedirect } from "@/lib/auth/guard";

export function proxy(request: NextRequest) {
  if (process.env.ARAG_DEV_USER_ID) return NextResponse.next(); // 認証を使わない開発構成
  const { pathname, search } = request.nextUrl;
  const to = authRedirect(pathname, search, Boolean(getSessionCookie(request)));
  return to ? NextResponse.redirect(new URL(to, request.url)) : NextResponse.next();
}

export const config = {
  // API・静的ファイル・画像は対象外
  matcher: ["/((?!api/|_next/|favicon\\.ico|.*\\.(?:png|jpg|jpeg|svg|ico|webp|txt|woff2?)$).*)"],
};
