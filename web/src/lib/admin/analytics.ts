/** 利用状況の分析（specs/012-analytics）の表示用の小さな関数。 */
import { ja } from "@/i18n/locales/ja";

export const PERIODS = [7, 30, 90] as const;
export type Period = (typeof PERIODS)[number];

const REASON_LABEL: Record<string, string> = {
  no_sources: "資料が見つからない",
  no_relevant_sources: "関連する資料がない",
  step_budget_exhausted: "調べる回数の上限",
  tool_failed: "検索の失敗",
  generation_failed: "生成の失敗",
};

export const reasonLabel = (r: string) => REASON_LABEL[r] ?? r;

const TAG_LABEL: Record<string, string> = {
  outdated: ja.chat.feedbackReasonOutdated,
  wrong: ja.chat.feedbackReasonWrong,
  no_source: ja.chat.feedbackReasonNoSource,
  irrelevant: ja.chat.feedbackReasonIrrelevant,
  other: ja.chat.feedbackReasonOther,
};

export const tagLabel = (t: string) => TAG_LABEL[t] ?? t;

/** 1 万未満は桁区切り、それ以上は K / M に縮める。 */
export function compact(n: number): string {
  if (n < 10_000) return n.toLocaleString("en-US");
  if (n < 1_000_000) return `${+(n / 1000).toFixed(1)}K`;
  return `${+(n / 1_000_000).toFixed(1)}M`;
}

export function formatRate(r: number | null | undefined): string {
  if (r == null) return "—";
  return `${+(r * 100).toFixed(1)}%`;
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return "—";
  if (ms < 59_950) return `${(Math.round(ms / 100) / 10).toFixed(1)} 秒`;
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)} 分 ${s % 60} 秒`;
}

/** y 軸の上限。1・2・4・5・8 × 10^k のうち max 以上で最小のもの（最低 4）。 */
export function niceMax(max: number): number {
  if (max <= 4) return 4;
  const p = 10 ** Math.floor(Math.log10(max));
  for (const m of [1, 2, 4, 5, 8, 10]) if (m * p >= max) return m * p;
  return 10 * p;
}

/** x 軸に出す日付。先頭と末尾を必ず含め、およそ n 個に間引く。 */
export function tickDates(dates: string[], n: number): string[] {
  if (dates.length <= n) return dates;
  const step = Math.ceil((dates.length - 1) / (n - 1));
  const out = dates.filter((_, i) => i % step === 0);
  const last = dates.at(-1)!;
  if (out.at(-1) !== last) {
    // 末尾と近すぎる目盛は落とす
    if (dates.length - 1 - dates.indexOf(out.at(-1)!) < step / 2) out.pop();
    out.push(last);
  }
  return out;
}
