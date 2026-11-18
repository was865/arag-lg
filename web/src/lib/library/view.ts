/** 文書ライブラリの表示用の純関数。 */
import type { KbInfo } from "@/hooks/use-kbs";
import { t } from "@/i18n";

export type StatusTone = "ok" | "busy" | "danger" | "muted";
export type StatusFilter = "all" | "busy" | "error";

/** Content.status（queued / running / ready / error / cancelled）→ 表示。 */
export function docStatus(status: string): { label: string; tone: StatusTone } {
  switch (status) {
    case "ready":
      return { label: t.library.statusReady, tone: "ok" };
    case "error":
      return { label: t.library.statusError, tone: "danger" };
    case "cancelled":
      return { label: t.library.statusCancelled, tone: "muted" };
    case "queued":
      return { label: t.library.statusQueued, tone: "busy" };
    default:
      return { label: t.library.statusRunning, tone: "busy" };
  }
}

/** 絞り込み → GET /v1/documents の status（カンマ区切り）。すべてなら指定しない。 */
export function filterStatuses(filter: StatusFilter): string | null {
  if (filter === "busy") return "queued,running";
  if (filter === "error") return "error,cancelled";
  return null;
}

/** アップロード先の KB。開いている KB に書けるならそこ、「すべて」なら個人 KB、無ければ最初の書ける KB。 */
export function uploadTarget(kbs: KbInfo[], kbId: string | null): KbInfo | null {
  const live = kbs.filter((k) => k.canWrite && k.status !== "archived" && !k.deletedAt);
  if (kbId) return live.find((k) => k.id === kbId) ?? null;
  return live.find((k) => k.kind === "personal") ?? live[0] ?? null;
}

export function kbLabel(kb: Pick<KbInfo, "kind" | "name"> | null | undefined): string {
  if (!kb) return t.library.allDocuments;
  return kb.kind === "personal" ? t.library.personalKb : kb.name;
}

/** 1.2 GB / 340 MB / 12 KB。 */
export function formatBytes(n: number): string {
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(1)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(n >= 10 * 1024 ** 2 ? 0 : 1)} MB`;
  if (n >= 1024) return `${Math.round(n / 1024)} KB`;
  return `${n} B`;
}

/** 2026/11/09 形式（今年なら 11/09）。 */
export function formatDate(iso: string, now = new Date()): string {
  const d = new Date(iso);
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return d.getFullYear() === now.getFullYear() ? `${mm}/${dd}` : `${d.getFullYear()}/${mm}/${dd}`;
}

const EXT_LABELS: Record<string, string> = {
  pdf: "PDF", docx: "Word", doc: "Word", xlsx: "Excel", xls: "Excel", pptx: "PowerPoint", ppt: "PowerPoint",
  md: "Markdown", txt: t.library.extText, csv: "CSV", html: "HTML", htm: "HTML", png: t.library.extImage, jpg: t.library.extImage, jpeg: t.library.extImage,
};

export interface FormatRow {
  label: string;
  documents: number;
  bytes: number;
}

/** 拡張子ごとの数 → 形式ごとの行（Word の doc/docx などはまとめる）。多い順に max 行、残りは「その他」。 */
export function formatRows(byExt: { ext: string; documents: number; bytes: number }[], max = 6): FormatRow[] {
  const merged = new Map<string, FormatRow>();
  for (const e of byExt) {
    const label = EXT_LABELS[e.ext] ?? (e.ext ? e.ext.toUpperCase() : t.library.extOther);
    const row = merged.get(label) ?? { label, documents: 0, bytes: 0 };
    row.documents += e.documents;
    row.bytes += e.bytes;
    merged.set(label, row);
  }
  const rows = [...merged.values()].sort((a, b) => b.documents - a.documents || a.label.localeCompare(b.label));
  if (rows.length <= max) return rows;
  const rest = rows.slice(max - 1).reduce(
    (acc, r) => ({ ...acc, documents: acc.documents + r.documents, bytes: acc.bytes + r.bytes }),
    { label: t.library.extOther, documents: 0, bytes: 0 },
  );
  return [...rows.slice(0, max - 1), rest];
}

/** 形式ごとの色（積み上げ棒と凡例）。朱（アクセント）とは別の、ファイルの種類を表す色。 */
const FORMAT_COLORS: Record<string, string> = {
  Markdown: "#6c7078", テキスト: "#8b8f97", PDF: "#c8442f", Word: "#2f5fb0", Excel: "#2f8a63", CSV: "#2f8a63",
  PowerPoint: "#d0772a", HTML: "#7a4f9a", 画像: "#1f7a85",
};

export interface FormatSegment extends FormatRow {
  color: string;
  /** 棒の中の幅（%）。少ない形式も見えるよう下限を付け、合計が 100 になるよう多い形式から引く */
  width: number;
}

/** 形式の内訳 → 1 本の積み上げ棒の区切り（specs/025 R46）。 */
export function formatSegments(rows: FormatRow[], minWidth = 2): FormatSegment[] {
  const total = rows.reduce((a, r) => a + r.documents, 0);
  if (total === 0) return [];
  const raw = rows.map((r) => Math.max(minWidth, (r.documents / total) * 100));
  const over = raw.reduce((a, w) => a + w, 0) - 100;
  // 下限で増えた分は、いちばん広い区切りから引く
  const widest = raw.indexOf(Math.max(...raw));
  return rows.map((r, i) => ({
    ...r,
    color: FORMAT_COLORS[r.label] ?? "#9a9da3",
    width: Math.round((i === widest ? raw[i] - over : raw[i]) * 100) / 100,
  }));
}

/** 頁の範囲の表示（p.3 / p.3–5）。頁が無ければ null。 */
export function pageLabel(start: number | null | undefined, end?: number | null): string | null {
  if (start == null) return null;
  return end != null && end !== start ? `p.${start}–${end}` : `p.${start}`;
}

/** 見出しの道筋（"A > B > C"）を段に分ける。 */
export function headingParts(path: string): string[] {
  return path.split(/\s*>\s*/).filter(Boolean);
}

/** 見出しの道筋を画面の区切り（›）で 1 行にする。 */
export function headingCrumb(path: string): string {
  return headingParts(path).join(" › ");
}
