/** メンバーの一覧と招待（specs/010-admin-members R1・R3）。 */
import { randomBytes } from "node:crypto";
import { memberActionError } from "@/lib/admin/members";
import { apiError, fromAuthError, logAdmin, requireAdmin } from "@/lib/admin/server";
import { getAuth } from "@/lib/auth/server";

export async function GET(request: Request): Promise<Response> {
  const session = await requireAdmin(request);
  if (session instanceof Response) return session;
  const q = new URL(request.url).searchParams.get("q")?.trim() ?? "";
  const auth = getAuth();
  try {
    // 名前とメールの両方で探す（Better Auth の検索は 1 項目ずつ）
    const fields = q ? (["email", "name"] as const) : ([undefined] as const);
    const seen = new Map<string, unknown>();
    for (const field of fields) {
      const res = await auth.api.listUsers({
        headers: request.headers,
        query: {
          limit: 500,
          sortBy: "createdAt",
          sortDirection: "asc",
          ...(field ? { searchField: field, searchValue: q, searchOperator: "contains" as const } : {}),
        },
      });
      for (const u of res.users) seen.set(u.id, u);
    }
    const users = [...seen.values()].map((raw) => {
      const u = raw as {
        id: string;
        name: string;
        email: string;
        role?: string | null;
        emailVerified: boolean;
        banned?: boolean | null;
        createdAt: Date | string;
      };
      return {
        id: u.id,
        name: u.name,
        email: u.email,
        role: u.role ?? "member",
        emailVerified: u.emailVerified,
        banned: Boolean(u.banned),
        createdAt: new Date(u.createdAt).toISOString(),
      };
    });
    return Response.json({ items: users, me: session.user.id, myRole: session.user.role });
  } catch (e) {
    return fromAuthError(e, "メンバーの一覧を取得できませんでした");
  }
}

export async function POST(request: Request): Promise<Response> {
  const session = await requireAdmin(request);
  if (session instanceof Response) return session;
  const body = (await request.json().catch(() => null)) as { email?: string; name?: string; role?: string } | null;
  const email = body?.email?.trim().toLowerCase() ?? "";
  const name = body?.name?.trim() ?? "";
  const role = body?.role ?? "member";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254) {
    return apiError(422, "invalid_email", "メールアドレスの形が正しくありません");
  }
  if (!name || name.length > 100) return apiError(422, "invalid_name", "名前を 1〜100 文字で入れてください");
  const denied = memberActionError({ id: session.user.id, role: session.user.role }, null, { kind: "invite", role });
  if (denied) return apiError(403, "forbidden", denied);

  const auth = getAuth();
  try {
    // 本人しか知らない乱数のパスワードで作り、設定リンクをメールで送る
    const created = await auth.api.createUser({
      headers: request.headers,
      body: { email, name, password: randomBytes(24).toString("base64url"), role: "member", data: { emailVerified: true } },
    });
    if (role !== "member") {
      await auth.api.setRole({ headers: request.headers, body: { userId: created.user.id, role: role as "admin" } });
    }
    await auth.api.requestPasswordReset({ body: { email, redirectTo: "/reset-password?invite=1" } });
    logAdmin(session, "member.invite", { target: created.user.id, role });
    return Response.json({ id: created.user.id }, { status: 201 });
  } catch (e) {
    return fromAuthError(e, "招待できませんでした");
  }
}
