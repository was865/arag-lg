/** 文書ライブラリの複数選択（specs/009-library-bulk）。 */

export function toggleId(sel: ReadonlySet<string>, id: string): Set<string> {
  const next = new Set(sel);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

/** Shift+クリック: 起点（anchor）から対象までを一覧の順で選ぶ。起点が無ければ対象だけ。 */
export function selectRange(
  sel: ReadonlySet<string>,
  order: readonly string[],
  anchor: string | null,
  target: string,
): Set<string> {
  const next = new Set(sel);
  const a = anchor ? order.indexOf(anchor) : -1;
  const b = order.indexOf(target);
  if (a < 0 || b < 0) {
    next.add(target);
    return next;
  }
  for (let i = Math.min(a, b); i <= Math.max(a, b); i++) next.add(order[i]!);
  return next;
}

/** API の一括操作は 1 回 500 件まで。 */
export function chunk<T>(items: readonly T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}
