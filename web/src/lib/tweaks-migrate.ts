/**
 * 保存済みの表示設定の移行（specs/025 R40）。
 * 旧版は既定値ごと localStorage に保存していたので、既定のアクセントを朱に替えても古い橙が残る。
 * 版の印（v）が無い保存値に限り、旧既定の橙を新しい既定へ 1 回だけ替える。
 * layout.tsx の初回描画前スクリプトも同じ判定をする（ちらつき防止）。
 */
import { DEFAULT_ACCENT } from "@/lib/constants";

export const TWEAKS_VERSION = 2;
export const LEGACY_DEFAULT_ACCENT = "#d97757";

export function migrateStoredTweaks<T extends { accent?: string; v?: number }>(stored: T): T & { v: number } {
  if (stored.v && stored.v >= TWEAKS_VERSION) return stored as T & { v: number };
  const accent = stored.accent?.toLowerCase() === LEGACY_DEFAULT_ACCENT ? DEFAULT_ACCENT : stored.accent;
  return { ...stored, ...(accent ? { accent } : {}), v: TWEAKS_VERSION };
}
