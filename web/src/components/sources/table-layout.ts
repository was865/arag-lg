/** 表の見た目の決め方（列の寄せ・折り返し）。描画から切り離して試験できるようにする。 */
import type { TableCell, TableModel } from "@/components/sources/parse-table-html";

/** 数値として読めるセル（12.5 / -3 / 1,200 / 86.4℃ / 42 L/min / 45%）。 */
const NUMERIC_RE = /^[-+−]?\d[\d,]*(\.\d+)?\s*(%|％|℃|°C|[A-Za-z/]{1,6})?$/;
/** 折り返さずに 1 行で見せる長さ（全角でおよそ 1 語） */
const SHORT_MAX = 10;

export function cellText(c: TableCell): string {
  return c.lines.map((line) => line.map((s) => s.text).join("")).join("\n").trim();
}

export type CellFit = "numeric" | "short" | "long";

export function cellFit(c: TableCell): CellFit {
  const text = cellText(c);
  if (NUMERIC_RE.test(text)) return "numeric";
  return text.length <= SHORT_MAX && !text.includes("\n") ? "short" : "long";
}

/** 列の数（最も多い行のセル数。colspan を数える）。 */
export function columnCount(model: TableModel): number {
  return Math.max(0, ...model.rows.map((r) => r.cells.reduce((n, c) => n + c.colspan, 0)));
}

/** 本文のセルがすべて数値の列（右寄せにする）。結合セルがある表は列の位置がずれるので判定しない。 */
export function numericColumns(model: TableModel): Set<number> {
  const spans = model.rows.some((r) => r.cells.some((c) => c.colspan > 1 || c.rowspan > 1));
  if (spans) return new Set();
  const body = model.rows.filter((r) => !r.cells.every((c) => c.header));
  const out = new Set<number>();
  for (let ci = 0; ci < columnCount(model); ci++) {
    const cells = body.map((r) => r.cells[ci]).filter((c): c is TableCell => Boolean(c) && cellText(c!) !== "");
    if (cells.length > 0 && cells.every((c) => cellFit(c) === "numeric")) out.add(ci);
  }
  return out;
}
