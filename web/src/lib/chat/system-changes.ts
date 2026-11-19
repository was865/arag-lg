/** 社内システムの「最新にする」の差（api の changes）を表示用にする（specs/033 R17）。 */

export type RecordChange =
  | { key: string; column: string; before: unknown; after: unknown }
  | { key: string; column: null; change: "added" | "removed" };

export interface ChangeView {
  key: string;
  column: string | null;
  before?: string;
  after?: string;
  /** 数の増減（数でなければ null）。added・removed は行の増減。 */
  dir: "up" | "down" | null;
  kind: "value" | "added" | "removed";
}

const asNumber = (v: unknown): number | null => {
  if (typeof v === "number") return v;
  if (typeof v === "string" && /^-?\d+(\.\d+)?$/.test(v.trim())) return Number(v);
  return null;
};

export function changeViews(changes: unknown): ChangeView[] {
  if (!Array.isArray(changes)) return [];
  const out: ChangeView[] = [];
  for (const c of changes as RecordChange[]) {
    if (!c || typeof c !== "object") continue;
    if (c.column === null) {
      out.push({ key: String(c.key), column: null, dir: null, kind: c.change === "removed" ? "removed" : "added" });
      continue;
    }
    const a = asNumber(c.before);
    const b = asNumber(c.after);
    out.push({
      key: String(c.key),
      column: String(c.column),
      before: String(c.before ?? ""),
      after: String(c.after ?? ""),
      dir: a != null && b != null && a !== b ? (b > a ? "up" : "down") : null,
      kind: "value",
    });
  }
  return out;
}
