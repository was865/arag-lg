/** 文書ライブラリの表示用の純関数。 */
import type { KbInfo } from "@/hooks/use-kbs";

export type StatusTone = "ok" | "busy" | "danger" | "muted";
export type StatusFilter = "all" | "busy" | "error";

/** Content.status（queued / running / ready / error / cancelled）→ 表示。 */
export function docStatus(status: string): { label: string; tone: StatusTone } {
  switch (status) {
    case "ready":
      return { label: "検索できます", tone: "ok" };
    case "error":
      return { label: "解析に失敗", tone: "danger" };
    case "cancelled":
      return { label: "取り消し", tone: "muted" };
    case "queued":
      return { label: "待機中", tone: "busy" };
    default:
      return { label: "解析中", tone: "busy" };
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
  if (!kb) return "すべての文書";
  return kb.kind === "personal" ? "個人ナレッジベース" : kb.name;
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
  md: "Markdown", txt: "テキスト", csv: "CSV", html: "HTML", htm: "HTML", png: "画像", jpg: "画像", jpeg: "画像",
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
    const label = EXT_LABELS[e.ext] ?? (e.ext ? e.ext.toUpperCase() : "その他");
    const row = merged.get(label) ?? { label, documents: 0, bytes: 0 };
    row.documents += e.documents;
    row.bytes += e.bytes;
    merged.set(label, row);
  }
  const rows = [...merged.values()].sort((a, b) => b.documents - a.documents || a.label.localeCompare(b.label));
  if (rows.length <= max) return rows;
  const rest = rows.slice(max - 1).reduce(
    (acc, r) => ({ ...acc, documents: acc.documents + r.documents, bytes: acc.bytes + r.bytes }),
    { label: "その他", documents: 0, bytes: 0 },
  );
  return [...rows.slice(0, max - 1), rest];
}
