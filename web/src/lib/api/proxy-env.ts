import "server-only";

/** 中継の設定（環境変数から）。既定は Better Auth のセッション → JWT（specs/006-auth R13・R17）。 */
import { allowedOrigins, getAuth } from "@/lib/auth/server";
import { TokenCache } from "@/lib/auth/token-cache";
import { forwardHeaders, type ProxyOptions } from "@/lib/api/proxy";

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
  // 監査ログに利用者の IP を残すための、API と共有する合言葉
  const forwardSecret = process.env.ARAG_FORWARD_SECRET || undefined;
  if (devUserId) return { baseUrl, devUserId, devRole: process.env.ARAG_DEV_ROLE ?? "admin", forwardSecret };
  return { baseUrl, authorize, allowedOrigins: allowedOrigins(), forwardSecret };
}

/** サーバで API を呼ぶときの見出し（共有ページなど、ログインは任意）。
 * セッションがあればその JWT、dev 構成なら利用者ヘッダ、どちらも無ければ空。 */
export async function serverApiHeaders(requestHeaders: Headers): Promise<Headers> {
  const opts = proxyOptionsFromEnv();
  const fwd = forwardHeaders(requestHeaders, opts.forwardSecret);
  if (opts.devUserId) {
    return new Headers({ "x-dev-user-id": opts.devUserId, "x-dev-role": opts.devRole ?? "member", ...fwd });
  }
  const auth = await authorize(new Request("http://internal/", { headers: requestHeaders }));
  const out = auth instanceof Response ? new Headers() : auth;
  for (const [k, v] of Object.entries(fwd)) out.set(k, v);
  return out;
}
