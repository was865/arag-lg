/** ツールの段階の表示で共通に使うもの（アイコン・状態・見出し・表の部品・判定）。 */
import { ActivityGlyph, activityOf } from "@/components/chat/activity-glyph";
import { formatMs } from "@/lib/utils";
import type { ToolCall, ToolName, ToolStatus } from "@/lib/types";
import type { Dictionary } from "@/i18n/dictionary";

export const LOG_DETAIL_MAX = 8;
export const VERIFY_DETAIL_MAX = 5;

/** 実測時間を持たない合成マーカーステップ。これらは親の LLM 呼び出しに内包される、
 *  あるいは即時の可視化ステップとして durationMs=0 固定で emit される（run.ts 参照）:
 *   - reasoning : 親 LLM 呼び出しに内包され独立した実測時間を持たない
 *   - skill     : skill 設定のメモリ内読込で実測スパンが無い
 *   - rewrite_query : クエリ改変はモデルの推論内で完了済み（reasoning 側に計上）
 *  これらは 0ms の誤表示を避けて duration バッジ自体を出さない
 *  （実測がある streaming reasoning は durationMs を持つため通常表示）。 */
export const MARKER_STEPS = new Set<ToolName>(["reasoning", "skill", "rewrite_query"]);

export function stepDurationLabel(step: ToolCall): string | null {
  if (MARKER_STEPS.has(step.name) && !step.durationMs) return null;
  // システムの処理は、実際に測った処理（続けて聞く質問・数字の照合・要約など）だけ時間を出す。0 は測っていない
  if (step.name === "system" && !step.durationMs) return null;
  return formatMs(step.durationMs);
}

export interface CandidateHit {
  title: string;
  heading: string;
  score: number;
}

export interface ExpandedHit {
  id: string;
  title: string;
  heading: string;
  score: number;
  page: number;
  blockType: string;
  expandedChars: number;
  preview: string;
}

export interface GradeCandidate {
  chunkId: string;
  title: string;
  heading: string;
  score: number;
  kept: boolean;
}

export interface VerifyDetail {
  text: string;
  citedNums: number[];
  verdict: "supported" | "unsupported" | "not_a_claim" | "unverified";
  reason: string | null;
}

export const TOOL_ICONS: Partial<Record<ToolName, React.ReactNode>> = {
  switch_model: (
    <path d="M3 5h9l-2.5-2.5M13 11H4l2.5 2.5" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
  ),
  read_image: (
    <>
      <rect x="2" y="3" width="12" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.3" fill="none" />
      <circle cx="5.75" cy="6.5" r="1.25" stroke="currentColor" strokeWidth="1.2" fill="none" />
      <path d="M2.5 11.5l3.5-3 2.5 2 2-1.5 3 2.5" stroke="currentColor" strokeWidth="1.3" fill="none" strokeLinejoin="round" />
    </>
  ),
  skill: <path d="M8 1.5l1.6 4.3 4.4 1.7-4.4 1.7L8 13.5l-1.6-4.3L2 7.5l4.4-1.7L8 1.5z" stroke="currentColor" strokeWidth="1.2" fill="none" strokeLinejoin="round" />,
  reasoning: (
    <>
      <path d="M8 2.5a4.5 4.5 0 0 1 2.7 8.1c-.5.4-.7.8-.7 1.4H6c0-.7-.2-1-.8-1.5A4.5 4.5 0 0 1 8 2.5z" stroke="currentColor" strokeWidth="1.3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6.2 14h3.6M6.5 7.2h3M8 5.7v3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </>
  ),
  calculate: (
    <>
      <rect x="3" y="1.5" width="10" height="13" rx="1.5" stroke="currentColor" strokeWidth="1.3" fill="none" />
      <path d="M5.5 4.5h5M5.5 8h1M9.5 8h1M5.5 11h1M9.5 11h1" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </>
  ),
  rewrite_query: <path d="M3 8h7M7 5l-3 3 3 3M13 4v8" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
  candidates: (
    <>
      <path d="M3 4h10M3 8h10M3 12h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </>
  ),
  vector_search: (
    <>
      <circle cx="7" cy="7" r="4" stroke="currentColor" strokeWidth="1.5" fill="none" />
      <path d="M10 10l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="7" cy="7" r="1.5" fill="currentColor" />
    </>
  ),
  retrieve: (
    <>
      <circle cx="7" cy="7" r="4" stroke="currentColor" strokeWidth="1.5" fill="none" />
      <path d="M10 10l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="7" cy="7" r="1.5" fill="currentColor" />
    </>
  ),
  answer: <path d="M3 4h10M3 8h10M3 12h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />,
  bm25_search: <path d="M2 4h12M2 8h8M2 12h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />,
  rerank: (
    <>
      <path d="M3 11l3-3 3 3 4-4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M10 4h3v3" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </>
  ),
  fetch_document: (
    <>
      <path d="M4 2h6l3 3v9H4V2z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinejoin="round" />
      <path d="M10 2v3h3M6 8h5M6 11h5" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" />
    </>
  ),
  work_calendar: (
    <>
      <rect x="2.5" y="3" width="11" height="10.5" rx="1.5" stroke="currentColor" strokeWidth="1.4" fill="none" />
      <path d="M2.5 6h11M5.5 1.8v2.4M10.5 1.8v2.4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="8" cy="9.5" r="1.1" fill="currentColor" />
    </>
  ),
  summarize: <path d="M3 4h10M3 8h10M3 12h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />,
  embed: (
    <>
      <circle cx="8" cy="8" r="5" stroke="currentColor" strokeWidth="1.5" fill="none" />
      <circle cx="8" cy="8" r="1.5" fill="currentColor" />
    </>
  ),
  expand: <path d="M3 6V3h3M13 6V3h-3M3 10v3h3M13 10v3h-3" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
  grade: <path d="M2.5 3.5h11l-4.3 5v4l-2.4-1.2V8.5L2.5 3.5z" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
  verify: (
    <>
      <path d="M8 2.2l4.5 1.8v3.6c0 2.7-1.9 4.6-4.5 5.4-2.6-.8-4.5-2.7-4.5-5.4V4L8 2.2z" stroke="currentColor" strokeWidth="1.3" fill="none" strokeLinejoin="round" />
      <path d="M6 7.8l1.5 1.5L10.3 6" stroke="currentColor" strokeWidth="1.3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </>
  ),
  // 質問の理解（質問を整理して検索クエリにする）: 吹き出しと光
  understand: (
    <>
      <path d="M2.5 3.5h8a1.5 1.5 0 0 1 1.5 1.5v4a1.5 1.5 0 0 1-1.5 1.5H7l-2.8 2.2V10.5H4A1.5 1.5 0 0 1 2.5 9V3.5z" stroke="currentColor" strokeWidth="1.3" fill="none" strokeLinejoin="round" />
      <path d="M13 1.8l.5 1.3 1.3.5-1.3.5-.5 1.3-.5-1.3-1.3-.5 1.3-.5.5-1.3z" fill="currentColor" />
    </>
  ),
  // 表の集計（条件で行を選び、合計を計算する）: 格子
  table_query: (
    <>
      <rect x="2" y="3" width="12" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.3" fill="none" />
      <path d="M2 6.5h12M2 9.8h12M6.2 3v10" stroke="currentColor" strokeWidth="1.2" />
    </>
  ),
  // 聞き返し（specs/031）: 吹き出しと疑問符
  ask_user: (
    <>
      <path d="M2.5 3.5h11v7H8l-3 2.5v-2.5H2.5v-7z" stroke="currentColor" strokeWidth="1.3" fill="none" strokeLinejoin="round" />
      <path d="M6.6 5.9a1.4 1.4 0 1 1 2 1.3c-.4.2-.6.5-.6.9" stroke="currentColor" strokeWidth="1.2" fill="none" strokeLinecap="round" />
      <circle cx="8" cy="9.2" r=".6" fill="currentColor" />
    </>
  ),
  // システムの処理（後ろで行った整形・制御）: 歯車
  system: (
    <>
      <circle cx="8" cy="8" r="2.2" stroke="currentColor" strokeWidth="1.3" fill="none" />
      <path d="M8 1.8v1.8M8 12.4v1.8M1.8 8h1.8M12.4 8h1.8M3.6 3.6l1.3 1.3M11.1 11.1l1.3 1.3M3.6 12.4l1.3-1.3M11.1 4.9l1.3-1.3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </>
  ),
  // 調べ残しの見直し（下書きを差し戻す）: 戻る矢印つきの文書
  review: (
    <>
      <path d="M4 2h6l3 3v9H4V2z" stroke="currentColor" strokeWidth="1.3" fill="none" strokeLinejoin="round" />
      <path d="M10.5 9.5H7m0 0l1.6-1.6M7 9.5l1.6 1.6" stroke="currentColor" strokeWidth="1.3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </>
  ),
  revise: (
    <>
      <path d="M10.5 3.2l2.3 2.3-6.6 6.6-2.9.6.6-2.9 6.6-6.6z" stroke="currentColor" strokeWidth="1.3" fill="none" strokeLinejoin="round" />
      <path d="M9.3 4.4l2.3 2.3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </>
  ),
};

export function StatusIcon({ status, t, name }: { status: ToolStatus; t: Dictionary; name?: ToolName }) {
  if (status === "running")
    // 回る輪でなく、いましていること（検索・読む・計算…）の絵を動かす
    return (
      <span className="grid h-4 w-4 place-items-center" aria-label={t.chat.statusRunning}>
        <ActivityGlyph activity={activityOf(name)} size={13} />
      </span>
    );
  if (status === "done")
    return (
      <span className="grid h-4 w-4 place-items-center text-accent" aria-label={t.chat.statusDone}>
        <svg viewBox="0 0 16 16" width="11" height="11">
          <path d="M3 8l3.5 3.5L13 5" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    );
  if (status === "pending")
    return (
      <span className="grid h-4 w-4 place-items-center" aria-label={t.chat.statusPending}>
        <span className="h-1.5 w-1.5 rounded-full bg-muted-2" />
      </span>
    );
  return (
    <span className="grid h-[14px] w-[14px] place-items-center rounded-full bg-danger text-mini font-bold text-white" aria-label={t.chat.statusError}>
      !
    </span>
  );
}

export const preCls =
  "m-0 whitespace-pre-wrap break-words rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 font-mono text-caption leading-[1.55] text-fg-2";

export const sectionLabelCls = "mb-1 eyebrow";

export function hasInputData(input: Record<string, unknown>): boolean {
  return Object.keys(input).length > 0;
}

export function isExpandable(step: ToolCall): boolean {
  return hasInputData(step.input) || step.output != null;
}

export function KeyValueGrid({ rows }: { rows: { k: string; v: React.ReactNode }[] }) {
  return (
    <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-[3px] rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 font-mono text-caption leading-[1.55]">
      {rows.map((r) => (
        <div key={r.k} className="contents">
          <span className="text-muted-2">{r.k}</span>
          <span className="text-fg tabular-nums">{r.v}</span>
        </div>
      ))}
    </div>
  );
}

export function formatTokenCount(n: unknown): string {
  if (typeof n !== "number" || !Number.isFinite(n)) return "—";
  if (n >= 1000) return `${(n / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return String(n);
}

export function tokenRows(output: Record<string, unknown>, t: Dictionary): { k: string; v: React.ReactNode }[] {
  const rows: { k: string; v: React.ReactNode }[] = [
    { k: t.chat.inputTokens, v: formatTokenCount(output.inputTokens) },
    { k: t.chat.outputTokens, v: formatTokenCount(output.outputTokens) },
    { k: t.chat.totalTokens, v: formatTokenCount(output.totalTokens) },
  ];
  if (typeof output.cachedInputTokens === "number" && output.cachedInputTokens > 0) {
    rows.push({ k: t.chat.cacheTokens, v: formatTokenCount(output.cachedInputTokens) });
  }
  return rows;
}

export function hasTokenUsage(output: Record<string, unknown>): boolean {
  return ["inputTokens", "outputTokens", "totalTokens", "cachedInputTokens"].some((key) => {
    const value = output[key];
    return typeof value === "number" && Number.isFinite(value);
  });
}

export function ModelBlock({ model }: { model: string }) {
  return (
    <div className="rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 font-mono text-footnote leading-[1.55] text-fg">
      {model}
    </div>
  );
}

export function verifyVerdictLabel(verdict: VerifyDetail["verdict"], t: Dictionary): string {
  if (verdict === "supported") return t.chat.verifyVerdictSupported;
  if (verdict === "unsupported") return t.chat.verifyVerdictUnsupported;
  if (verdict === "unverified") return t.chat.verifyVerdictUnverified;
  return t.chat.verifyVerdictNotClaim;
}

export function verifyVerdictChipClass(verdict: VerifyDetail["verdict"]): string {
  if (verdict === "unsupported") {
    return "border border-accent bg-accent-soft text-accent";
  }
  if (verdict === "unverified") {
    return "border border-divider-strong bg-surface text-muted";
  }
  return "border border-divider bg-divider text-muted";
}

export function inputSectionLabel(step: ToolCall, t: Dictionary): string {
  if (step.name === "answer" || step.name === "reasoning" || step.name === "verify" || step.name === "revise") {
    return t.chat.sectionModel;
  }
  return t.chat.sectionInput;
}

export function outputSectionLabel(step: ToolCall, t: Dictionary): string {
  if (step.name === "answer" || step.name === "verify" || step.name === "revise") {
    return t.chat.sectionUsedTokens;
  }
  if (step.name === "reasoning") return t.chat.sectionReasoning;
  return t.chat.sectionOutput;
}


export const boxCls = "rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 text-footnote leading-[1.55] text-fg-2";

/** システムが先に行った検索の札（モデルが自分で行った検索と見分ける）。 */
export function AutoBadge({ t }: { t: Dictionary }) {
  return (
    <span
      title={t.chat.bySystemHint}
      className="shrink-0 rounded-full border-[0.5px] border-divider-strong px-1.5 py-px text-mini font-medium leading-none text-muted"
    >
      {t.chat.bySystem}
    </span>
  );
}

export function isBySystem(step: ToolCall): boolean {
  return step.input.by === "system";
}
