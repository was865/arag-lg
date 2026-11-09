import { describe, expect, it } from "vitest";
import { memberActionError, memberStatus, type MemberAction } from "@/lib/admin/members";

const owner = { id: "o", role: "owner" };
const admin = { id: "a", role: "admin" };
const admin2 = { id: "a2", role: "admin" };
const member = { id: "m", role: "member" };

const ok = (actor: typeof owner, target: typeof owner | null, action: MemberAction) =>
  memberActionError(actor, target, action) === null;

describe("memberActionError", () => {
  it("member は何もできない", () => {
    expect(ok(member, null, { kind: "invite", role: "member" })).toBe(false);
    expect(ok(member, { id: "x", role: "member" }, { kind: "ban" })).toBe(false);
  });
  it("自分自身・owner は対象にできない", () => {
    expect(ok(owner, owner, { kind: "ban" })).toBe(false);
    expect(ok(admin, admin, { kind: "role", role: "member" })).toBe(false);
    expect(ok(admin, owner, { kind: "ban" })).toBe(false);
    expect(ok(owner, { id: "o2", role: "owner" }, { kind: "role", role: "admin" })).toBe(false);
  });
  it("owner の役割は付けられない", () => {
    expect(ok(owner, member, { kind: "role", role: "owner" })).toBe(false);
    expect(ok(owner, null, { kind: "invite", role: "owner" })).toBe(false);
  });
  it("admin を対象にする操作と admin としての招待は owner だけ", () => {
    expect(ok(owner, member, { kind: "role", role: "admin" })).toBe(true);
    expect(ok(owner, admin, { kind: "role", role: "member" })).toBe(true);
    expect(ok(owner, admin, { kind: "ban" })).toBe(true);
    expect(ok(owner, null, { kind: "invite", role: "admin" })).toBe(true);
    expect(ok(admin, member, { kind: "role", role: "admin" })).toBe(false);
    expect(ok(admin, admin2, { kind: "ban" })).toBe(false);
    expect(ok(admin, admin2, { kind: "unban" })).toBe(false);
    expect(ok(admin, null, { kind: "invite", role: "admin" })).toBe(false);
  });
  it("admin は member の招待・停止・再開ができる", () => {
    expect(ok(admin, null, { kind: "invite", role: "member" })).toBe(true);
    expect(ok(admin, member, { kind: "ban" })).toBe(true);
    expect(ok(admin, member, { kind: "unban" })).toBe(true);
  });
  it("拒否の理由は日本語", () => {
    expect(memberActionError(admin, owner, { kind: "ban" })).toMatch(/owner/);
  });
});

describe("memberStatus", () => {
  it("停止 > 未確認 > 有効", () => {
    expect(memberStatus({ banned: true, emailVerified: false })).toBe("banned");
    expect(memberStatus({ banned: false, emailVerified: false })).toBe("unverified");
    expect(memberStatus({ banned: null, emailVerified: true })).toBe("active");
  });
});
