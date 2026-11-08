/** 空状態に出す件数（`GET /v1/documents/stats` と KB 一覧から作る）。 */
export interface WorkspaceStats {
  indexedDocumentCount: number;
  totalDocumentCount: number;
  kbCount: number;
  lastSyncedAt: string | null;
}

export const EMPTY_STATS: WorkspaceStats = {
  indexedDocumentCount: 0,
  totalDocumentCount: 0,
  kbCount: 0,
  lastSyncedAt: null,
};

export interface DocumentStatsPayload {
  documents?: unknown;
  by_status?: Record<string, unknown>;
}

const intCount = (value: unknown) => {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? Math.max(0, Math.trunc(n)) : 0;
};

export function normalizeStats(payload: DocumentStatsPayload, kbCount: number): WorkspaceStats {
  return {
    indexedDocumentCount: intCount(payload.by_status?.ready),
    totalDocumentCount: intCount(payload.documents),
    kbCount,
    lastSyncedAt: null,
  };
}

export function formatLastSynced(value: string | null, now = new Date()): string {
  const never = "—";
  if (!value) return never;
  const ts = new Date(value).getTime();
  if (!Number.isFinite(ts)) return never;
  const minutes = Math.floor(Math.max(0, now.getTime() - ts) / 60_000);
  if (minutes < 1) return "たった今";
  if (minutes < 60) return `${minutes}分前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}時間前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}日前`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}ヶ月前`;
  return `${Math.floor(months / 12)}年前`;
}
