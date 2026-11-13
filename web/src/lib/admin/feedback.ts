/** 技術者への報告（specs/028 R13〜R16）。一覧・詳細の型と、診断用の JSON。 */
import type { components } from "@/lib/api/schema";
import { ja } from "@/i18n/locales/ja";

export type FeedbackRow = components["schemas"]["FeedbackRow"];
export type FeedbackDetail = components["schemas"]["FeedbackDetail"];
export type FeedbackStatus = FeedbackRow["status"];

export const statusLabel = (s: FeedbackStatus) => (s === "resolved" ? ja.admin.statusResolved : ja.admin.statusOpen);

// 秘密や個人を指す値を持ちうる鍵（ステップの入力・出力に紛れても診断用の JSON には入れない）
const SECRET_KEY = /(api[_-]?key|secret|password|passwd|token$|authorization|cookie|headers?$|email|e-mail|user_id|resolved_by)/i;

function scrub(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(scrub);
  if (v && typeof v === "object") {
    return Object.fromEntries(
      Object.entries(v as Record<string, unknown>)
        .filter(([k]) => !SECRET_KEY.test(k))
        .map(([k, x]) => [k, scrub(x)]),
    );
  }
  // 値に紛れたメールアドレスも伏せる
  return typeof v === "string" ? v.replace(/[\w.+-]+@[\w-]+(\.[\w-]+)+/g, "（メールアドレス）") : v;
}

/**
 * 診断用にコピーする JSON（report_version 1）。報告者は表示名だけ。利用者 ID・メールアドレス・
 * API キーなどの秘密は入れない（.env 由来の値は API の応答にもともと無い）。
 */
export function diagnostics(d: FeedbackDetail, reporterName: string | null) {
  const m = d.message;
  return {
    report_version: 1 as const,
    feedback: {
      id: d.id,
      rating: d.rating,
      reason_tags: d.reason_tags,
      comment: scrub(d.comment) as string | null,
      status: d.status,
      reporter: reporterName,
      created_at: d.created_at,
      updated_at: d.updated_at,
    },
    thread: { id: d.thread_id, title: d.thread_title },
    message: {
      id: m.id,
      query: scrub(m.query) as string,
      answer: scrub(m.answer) as string,
      status: m.status,
      model_id: m.model_id,
      duration_ms: m.duration_ms,
      tokens_in: m.tokens_in,
      tokens_out: m.tokens_out,
      no_answer_reason: m.no_answer_reason,
      created_at: m.created_at,
      citation_map: m.citation_map,
      sources: scrub(m.sources) as typeof m.sources,
      steps: scrub(m.steps) as typeof m.steps,
    },
  };
}
