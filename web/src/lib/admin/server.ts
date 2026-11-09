import "server-only";

/** 管理 API の共通部品（specs/010-admin-members）。 */
import { authBaseUrl, getAuth } from "@/lib/auth/server";

export type AdminSession = NonNullable<Awaited<ReturnType<ReturnType<typeof getAuth>["api"]["getSession"]>>>;

export const apiError = (status: number, code: string, message: string) =>
  Response.json({ error: { code, message } }, { status });

/** owner・admin のセッション。違えば応答（401・403）を返す。状態を変える要求は Origin も確かめる。 */
export async function requireAdmin(request: Request): Promise<AdminSession | Response> {
  if (request.method !== "GET") {
    const origin = request.headers.get("origin");
    if (origin && origin !== authBaseUrl()) return apiError(403, "forbidden_origin", "許可されていない送信元です");
  }
  const session = await getAuth().api.getSession({ headers: request.headers });
  if (!session) return apiError(401, "unauthenticated", "ログインが必要です");
  const role = session.user.role;
  if (role !== "owner" && role !== "admin") return apiError(403, "forbidden", "管理者だけが使えます");
  return session;
}

/** Better Auth の APIError などを利用者向けの応答にする。 */
export function fromAuthError(e: unknown, fallback: string): Response {
  const err = e as { status?: unknown; statusCode?: number; body?: { message?: string; code?: string } };
  const status = typeof err.statusCode === "number" ? err.statusCode : 400;
  const code = err.body?.code ?? "";
  if (code === "USER_ALREADY_EXISTS" || code === "USER_ALREADY_EXISTS_USE_ANOTHER_EMAIL") {
    return apiError(409, "already_exists", "このメールアドレスは既に登録されています");
  }
  console.error("[admin]", fallback, e);
  return apiError(status >= 400 && status < 600 ? status : 500, "admin_failed", fallback);
}

export function logAdmin(session: AdminSession, action: string, detail: Record<string, unknown>): void {
  // 監査ログ画面は別 spec。ここではサーバのログに残す（R8）
  console.info(`[admin] ${JSON.stringify({ actor: session.user.id, action, ...detail, at: new Date().toISOString() })}`);
}
