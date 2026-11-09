/** 共有リストの見方（specs/024）。画面で使う純関数。 */

export type ShareRole = "viewer" | "editor" | "manager";
export type SubjectType = "everyone" | "department" | "user";

export interface Share {
  subject_type: SubjectType;
  subject_id: string;
  role: ShareRole;
}

export const ROLE_LABEL: Record<ShareRole, string> = { viewer: "閲覧", editor: "編集", manager: "管理" };
export const ROLE_HINT: Record<ShareRole, string> = {
  viewer: "読む・質問の範囲に入る",
  editor: "文書を追加・変更・削除できる",
  manager: "共有の変更・名前変更・アーカイブもできる",
};
const RANK: Record<ShareRole, number> = { viewer: 1, editor: 2, manager: 3 };

export function stronger(a: ShareRole | undefined, b: ShareRole): ShareRole {
  return a && RANK[a] >= RANK[b] ? a : b;
}

/** 人ごとのいちばん強い役割。everyone は社内の全員の user_id（停止中は除いたもの）。 */
export function effectiveRoles(
  shares: Share[],
  departmentMembers: Record<string, string[]>,
  everyone: string[],
): Map<string, ShareRole> {
  const out = new Map<string, ShareRole>();
  const give = (uid: string, role: ShareRole) => out.set(uid, stronger(out.get(uid), role));
  for (const s of shares) {
    if (s.subject_type === "everyone") everyone.forEach((u) => give(u, s.role));
    else if (s.subject_type === "department") (departmentMembers[s.subject_id] ?? []).forEach((u) => give(u, s.role));
    else give(s.subject_id, s.role);
  }
  return out;
}

/** 共有リストを変えると見られなくなる人・役割が下がる人（R8）。 */
export function accessLoss(
  before: Share[],
  after: Share[],
  departmentMembers: Record<string, string[]>,
  everyone: string[],
): { lost: string[]; lowered: string[] } {
  const a = effectiveRoles(before, departmentMembers, everyone);
  const b = effectiveRoles(after, departmentMembers, everyone);
  const lost: string[] = [];
  const lowered: string[] = [];
  for (const [uid, role] of a) {
    const next = b.get(uid);
    if (!next) lost.push(uid);
    else if (RANK[next] < RANK[role]) lowered.push(uid);
  }
  return { lost: lost.sort(), lowered: lowered.sort() };
}

/** 見出しに出す 1 行の要約（R11）。例「製造部・品質保証部 ほか 2 名が利用」「社内の全員が閲覧 · 編集 3」。 */
export function shareSummary(
  shares: Share[],
  departmentName: (id: string) => string,
  editorsCount: number,
): string {
  const everyone = shares.some((s) => s.subject_type === "everyone");
  const depts = shares.filter((s) => s.subject_type === "department").map((s) => departmentName(s.subject_id));
  const people = shares.filter((s) => s.subject_type === "user").length;
  let who: string;
  if (everyone) who = "社内の全員が閲覧";
  else {
    const shown = depts.slice(0, 2);
    const rest = depts.length - shown.length + people;
    const head = shown.join("・");
    who = head ? `${head}${rest > 0 ? ` ほか ${rest} 件` : ""}が利用` : `${people} 名が利用`;
  }
  return editorsCount > 0 ? `${who} · 編集できる人 ${editorsCount} 名` : who;
}

/** 共有リストの並び（全員 → 部門 → 人。同じ種類は名前順）。 */
export function sortShares(shares: Share[], label: (s: Share) => string): Share[] {
  const order: Record<SubjectType, number> = { everyone: 0, department: 1, user: 2 };
  return [...shares].sort(
    (a, b) => order[a.subject_type] - order[b.subject_type] || label(a).localeCompare(label(b), "ja"),
  );
}

export function sameShares(a: Share[], b: Share[]): boolean {
  const key = (s: Share) => `${s.subject_type}:${s.subject_id}:${s.role}`;
  const ka = a.map(key).sort().join("|");
  return ka === b.map(key).sort().join("|");
}

/** 送る前の確かめ（サーバーと同じ規則。R6・R7）。問題が無ければ null。 */
export function shareError(shares: Share[]): string | null {
  if (shares.some((s) => s.subject_type === "everyone" && s.role !== "viewer")) return "全員には閲覧だけを付けられます";
  if (!shares.some((s) => s.role === "manager")) return "管理できる人（部門）を 1 つ以上残してください";
  return null;
}

/** 「なぜ見られるか」の 1 行（R13）。例「製造部のメンバーとして（閲覧）」。 */
export function reasonLabel(
  r: { subject_type: SubjectType; role: ShareRole; subject_id: string },
  departmentName: (id: string) => string,
): string {
  const how =
    r.subject_type === "everyone"
      ? "社内の全員として"
      : r.subject_type === "department"
        ? `${departmentName(r.subject_id)}のメンバーとして`
        : "本人に付与";
  return `${how}（${ROLE_LABEL[r.role]}）`;
}
