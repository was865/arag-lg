/** メンバー管理の権限の規則（specs/010-admin-members R4・R5）。サーバの Route Handler が使う。 */

export type Role = "owner" | "admin" | "member";
export const ASSIGNABLE_ROLES = ["member", "admin"] as const;
export type AssignableRole = (typeof ASSIGNABLE_ROLES)[number];

export const ROLE_LABEL: Record<Role, string> = { owner: "オーナー", admin: "管理者", member: "メンバー" };

export type MemberAction =
  | { kind: "invite"; role: string }
  | { kind: "role"; role: string }
  | { kind: "ban" }
  | { kind: "unban" };

interface Who {
  id: string;
  role?: string | null;
}

const isAdmin = (r?: string | null) => r === "owner" || r === "admin";

/** 許されないなら理由、許されるなら null。target は招待のときだけ null。 */
export function memberActionError(actor: Who, target: Who | null, action: MemberAction): string | null {
  if (!isAdmin(actor.role)) return "管理者だけが操作できます";
  if ("role" in action && !(ASSIGNABLE_ROLES as readonly string[]).includes(action.role)) {
    return "付けられる役割はメンバーか管理者です";
  }
  if (action.kind === "invite") {
    return action.role === "admin" && actor.role !== "owner" ? "管理者として招待できるのは owner だけです" : null;
  }
  if (!target) return "対象の利用者が見つかりません";
  if (target.id === actor.id) return "自分自身には行えません";
  if (target.role === "owner") return "owner は変更できません";
  const touchesAdmin = target.role === "admin" || (action.kind === "role" && action.role === "admin");
  if (touchesAdmin && actor.role !== "owner") return "管理者の変更は owner だけが行えます";
  return null;
}

export type MemberStatus = "active" | "unverified" | "banned";

export function memberStatus(u: { banned?: boolean | null; emailVerified: boolean }): MemberStatus {
  if (u.banned) return "banned";
  return u.emailVerified ? "active" : "unverified";
}

export const STATUS_LABEL: Record<MemberStatus, string> = { active: "有効", unverified: "未確認", banned: "停止中" };
