/**
 * 保存済みの表示設定の移行（specs/025 R40）。
 * 旧版は既定値ごと localStorage に保存していたので、既定のアクセントを朱に替えても古い橙が残る。
 * 版の印（v）が無い保存値に限り、旧既定の橙を新しい既定へ 1 回だけ替える。
 * 選べなくなった色（橙・緑・青・紫。R48）は、版に関わらず近い色へ移す（lib/accent の RETIRED_ACCENTS）。
 * layout.tsx の初回描画前スクリプトも同じ判定をする（ちらつき防止）。
 */
import { DEFAULT_ACCENT } from "@/lib/constants";
import { RETIRED_ACCENTS } from "@/lib/accent";

export const TWEAKS_VERSION = 2;
export const LEGACY_DEFAULT_ACCENT = "#d97757";

export function migrateStoredTweaks<T extends { accent?: string; v?: number }>(stored: T): T & { v: number } {
  const key = stored.accent?.toLowerCase();
  const legacy = !(stored.v && stored.v >= TWEAKS_VERSION) && key === LEGACY_DEFAULT_ACCENT;
  const accent = legacy ? DEFAULT_ACCENT : key && RETIRED_ACCENTS[key] ? RETIRED_ACCENTS[key] : stored.accent;
  return { ...stored, ...(accent ? { accent } : {}), v: Math.max(stored.v ?? 0, TWEAKS_VERSION) };
}
