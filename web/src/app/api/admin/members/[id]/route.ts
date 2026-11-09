/** メンバーの役割の変更・停止・再開・招待の再送（specs/010-admin-members R4〜R6）。 */
import { memberActionError, type MemberAction } from "@/lib/admin/members";
import { apiError, fromAuthError, logAdmin, requireAdmin } from "@/lib/admin/server";
import { getAuth } from "@/lib/auth/server";

type Ctx = { params: Promise<{ id: string }> };

export async function PATCH(request: Request, ctx: Ctx): Promise<Response> {
  const session = await requireAdmin(request);
  if (session instanceof Response) return session;
  const { id } = await ctx.params;
  const body = (await request.json().catch(() => null)) as {
    role?: string;
    banned?: boolean;
    resendInvite?: boolean;
  } | null;
  const action: MemberAction | null =
    typeof body?.role === "string"
      ? { kind: "role", role: body.role }
      : body?.banned === true
        ? { kind: "ban" }
        : body?.banned === false
          ? { kind: "unban" }
          : body?.resendInvite
            ? { kind: "unban" } // 再送は再開と同じ権限（対象を扱えるか）で判定する
            : null;
  if (!action) return apiError(422, "invalid_body", "変更する内容がありません");

  const auth = getAuth();
  let target: { id: string; role?: string | null; email: string };
  try {
    target = (await auth.api.getUser({ headers: request.headers, query: { id } })) as typeof target;
  } catch {
    return apiError(404, "not_found", "利用者が見つかりません");
  }
  const denied = memberActionError({ id: session.user.id, role: session.user.role }, target, action);
  if (denied) return apiError(403, "forbidden", denied);

  try {
    if (body?.resendInvite) {
      await auth.api.requestPasswordReset({ body: { email: target.email, redirectTo: "/reset-password?invite=1" } });
      logAdmin(session, "member.resend_invite", { target: id });
    } else if (action.kind === "role") {
      await auth.api.setRole({ headers: request.headers, body: { userId: id, role: action.role as "admin" | "member" } });
      logAdmin(session, "member.role", { target: id, role: action.role });
    } else if (action.kind === "ban") {
      // 停止はセッションもすべて失効させる（R6）
      await auth.api.banUser({ headers: request.headers, body: { userId: id, banReason: "管理者が停止" } });
      logAdmin(session, "member.ban", { target: id });
    } else {
      await auth.api.unbanUser({ headers: request.headers, body: { userId: id } });
      logAdmin(session, "member.unban", { target: id });
    }
    return Response.json({ ok: true });
  } catch (e) {
    return fromAuthError(e, "変更できませんでした");
  }
}
