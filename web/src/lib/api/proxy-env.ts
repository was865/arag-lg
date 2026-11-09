import "server-only";

/** 中継の設定（環境変数から）。既定は Better Auth のセッション → JWT（specs/006-auth R13・R17）。 */
import { authBaseUrl, getAuth } from "@/lib/auth/server";
import { TokenCache } from "@/lib/auth/token-cache";
import type { ProxyOptions } from "@/lib/api/proxy";

const tokens = new TokenCache();

const unauthenticated = () =>
  Response.json({ error: { code: "unauthenticated", message: "ログインが必要です" } }, { status: 401 });

async function authorize(request: Request): Promise<Headers | Response> {
  const auth = getAuth();
  const session = await auth.api.getSession({ headers: request.headers });
  if (!session) return unauthenticated();
  // 確認状態・ロールが変わったら別の JWT にする（古い主張を使い回さない）
  const { user } = session;
  const key = `${session.session.id}:${user.emailVerified ? 1 : 0}:${user.role ?? ""}`;
  try {
    const token = await tokens.get(key, async () => (await auth.api.getToken({ headers: request.headers })).token);
    return new Headers({ authorization: `Bearer ${token}` });
  } catch {
    return unauthenticated();
  }
}

export function proxyOptionsFromEnv(): ProxyOptions {
  const baseUrl = process.env.API_BASE_URL ?? "http://localhost:8100";
  const devUserId = process.env.ARAG_DEV_USER_ID;
  if (devUserId) return { baseUrl, devUserId, devRole: process.env.ARAG_DEV_ROLE ?? "admin" };
  return { baseUrl, authorize, allowedOrigins: [authBaseUrl()] };
}
