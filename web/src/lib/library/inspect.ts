/** 解析の対照（specs/030-parse-inspection）の純粋関数。 */
import type { components } from "@/lib/api/schema";

type S = components["schemas"];
export type ParseReport = S["ParseReportOut"];
export type ParseWarning = S["ParseWarningOut"];
export type ChunkOut = S["ChunkOut"];

export interface Box {
  page: number;
  bbox: number[];
  origin?: string;
}

export interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** Docling の枠（頁の座標）を、画面の頁（左上が原点、scale 倍）での矩形にする（R9）。
 * `BOTTOMLEFT` は y が下から上へ数えるので、頁の高さで反転する。 */
export function boxToRect(box: Box, pageHeight: number, scale: number): Rect {
  const [l = 0, t = 0, r = 0, b = 0] = box.bbox;
  const top = box.origin === "TOPLEFT" ? Math.min(t, b) : pageHeight - Math.max(t, b);
  return {
    left: Math.min(l, r) * scale,
    top: top * scale,
    width: Math.abs(r - l) * scale,
    height: Math.abs(t - b) * scale,
  };
}

/** 頁に載っているチャンク。枠があれば枠の頁、無ければ頁の範囲で決める。 */
export function chunksOnPage(chunks: ChunkOut[], page: number): ChunkOut[] {
  return chunks.filter((c) => {
    const boxes = c.boxes as unknown as Box[];
    if (boxes.length > 0) return boxes.some((b) => b.page === page);
    if (c.page_start == null) return false;
    return page >= c.page_start && page <= (c.page_end ?? c.page_start);
  });
}

/** チャンクの枠のうち、その頁にあるもの。 */
export function boxesOnPage(chunk: ChunkOut, page: number): Box[] {
  return (chunk.boxes as unknown as Box[]).filter((b) => b.page === page);
}

/** チャンクを選んだとき最初に見せる頁。 */
export function firstPageOf(chunk: ChunkOut): number | null {
  const boxes = chunk.boxes as unknown as Box[];
  return boxes[0]?.page ?? chunk.page_start ?? null;
}

/** 頁ごとの警告（warn 以上は重く出す）。頁の無い警告は null の鍵にまとめる。 */
export function warningsByPage(report: ParseReport): Map<number | null, ParseWarning[]> {
  const out = new Map<number | null, ParseWarning[]>();
  for (const w of report.warnings) {
    const list = out.get(w.page) ?? [];
    list.push(w);
    out.set(w.page, list);
  }
  return out;
}

export const WARNING_LABEL: Record<string, string> = {
  empty_page: "空の頁",
  image_only_page: "図だけの頁",
  garbled_text: "文字化けの疑い",
  table_sparse: "崩れた表の疑い",
  missing_asset: "図の画像なし",
  bbox_out_of_page: "枠が頁の外",
  no_text: "文字なし",
  chunk_page_gap: "チャンクなし",
  docling_partial: "一部だけ成功",
  docling_errors: "Docling のエラー",
};

export function warningLabel(code: string): string {
  return WARNING_LABEL[code] ?? code;
}

export const BLOCK_LABEL: Record<string, string> = {
  text: "本文",
  table: "表",
  figure: "図",
  code: "コード",
  formula: "数式",
  list: "リスト",
};

export const CONTEXT_SOURCE_LABEL: Record<string, string> = {
  llm: "モデルが付与",
  heading: "見出しから作成",
};

/** 前後の頁（端では null）。 */
export function adjacentPage(pages: number[], page: number, dir: -1 | 1): number | null {
  const i = pages.indexOf(page);
  if (i < 0) return pages[0] ?? null;
  return pages[i + dir] ?? null;
}

/** 今の頁より後ろで、warn の警告がある最初の頁（無ければ先頭から探し直す）。 */
export function nextWarningPage(report: ParseReport | null, page: number): number | null {
  if (!report) return null;
  const warned = [...new Set(report.warnings.filter((w) => w.severity === "warn" && w.page != null).map((w) => w.page!))].sort(
    (a, b) => a - b,
  );
  return warned.find((p) => p > page) ?? warned[0] ?? null;
}

/** 見出しの道筋（"A > B > C"）を画面の区切り（›）に直す。 */
export function headingCrumb(path: string): string {
  return path.split(/\s*>\s*/).filter(Boolean).join(" › ");
}
