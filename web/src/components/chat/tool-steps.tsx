"use client";

import { useState } from "react";
import { parseRetrieveHits } from "@/lib/chat/evidence";
import { SearchDetail, searchHits } from "@/components/chat/search-detail";
import { ActivityGlyph, activityOf } from "@/components/chat/activity-glyph";
import { cn, formatMs } from "@/lib/utils";
import { Icon } from "@/components/icons";
import type { RerankHit, ToolCall, ToolName, ToolStatus, ToolView } from "@/lib/types";
import { useT } from "@/i18n/context";
import { interpolate } from "@/i18n/interpolate";
import type { Dictionary } from "@/i18n/dictionary";

const LOG_DETAIL_MAX = 8;
const VERIFY_DETAIL_MAX = 5;

/** 実測時間を持たない合成マーカーステップ。これらは親の LLM 呼び出しに内包される、
 *  あるいは即時の可視化ステップとして durationMs=0 固定で emit される（run.ts 参照）:
 *   - reasoning : 親 LLM 呼び出しに内包され独立した実測時間を持たない
 *   - skill     : skill 設定のメモリ内読込で実測スパンが無い
 *   - rewrite_query : クエリ改変はモデルの推論内で完了済み（reasoning 側に計上）
 *  これらは 0ms の誤表示を避けて duration バッジ自体を出さない
 *  （実測がある streaming reasoning は durationMs を持つため通常表示）。 */
const MARKER_STEPS = new Set<ToolName>(["reasoning", "skill", "rewrite_query"]);

function stepDurationLabel(step: ToolCall): string | null {
  if (MARKER_STEPS.has(step.name) && !step.durationMs) return null;
  return formatMs(step.durationMs);
}

interface CandidateHit {
  title: string;
  heading: string;
  score: number;
}

interface ExpandedHit {
  id: string;
  title: string;
  heading: string;
  score: number;
  page: number;
  blockType: string;
  expandedChars: number;
  preview: string;
}

interface GradeCandidate {
  chunkId: string;
  title: string;
  heading: string;
  score: number;
  kept: boolean;
}

interface VerifyDetail {
  text: string;
  citedNums: number[];
  verdict: "supported" | "unsupported" | "not_a_claim" | "unverified";
  reason: string | null;
}

const TOOL_ICONS: Partial<Record<ToolName, React.ReactNode>> = {
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

function StatusIcon({ status, t, name }: { status: ToolStatus; t: Dictionary; name?: ToolName }) {
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

const preCls =
  "m-0 whitespace-pre-wrap break-words rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 font-mono text-caption leading-[1.55] text-fg-2";

const sectionLabelCls = "mb-1 text-mini font-semibold uppercase tracking-[0.06em] text-muted";

function hasInputData(input: Record<string, unknown>): boolean {
  return Object.keys(input).length > 0;
}

function isExpandable(step: ToolCall): boolean {
  return hasInputData(step.input) || step.output != null;
}

function KeyValueGrid({ rows }: { rows: { k: string; v: React.ReactNode }[] }) {
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

function formatTokenCount(n: unknown): string {
  if (typeof n !== "number" || !Number.isFinite(n)) return "—";
  if (n >= 1000) return `${(n / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return String(n);
}

function tokenRows(output: Record<string, unknown>, t: Dictionary): { k: string; v: React.ReactNode }[] {
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

function hasTokenUsage(output: Record<string, unknown>): boolean {
  return ["inputTokens", "outputTokens", "totalTokens", "cachedInputTokens"].some((key) => {
    const value = output[key];
    return typeof value === "number" && Number.isFinite(value);
  });
}

function ModelBlock({ model }: { model: string }) {
  return (
    <div className="rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 font-mono text-footnote leading-[1.55] text-fg">
      {model}
    </div>
  );
}

function verifyVerdictLabel(verdict: VerifyDetail["verdict"], t: Dictionary): string {
  if (verdict === "supported") return t.chat.verifyVerdictSupported;
  if (verdict === "unsupported") return t.chat.verifyVerdictUnsupported;
  if (verdict === "unverified") return t.chat.verifyVerdictUnverified;
  return t.chat.verifyVerdictNotClaim;
}

function verifyVerdictChipClass(verdict: VerifyDetail["verdict"]): string {
  if (verdict === "unsupported") {
    return "border border-accent bg-accent-soft text-accent";
  }
  if (verdict === "unverified") {
    return "border border-divider-strong bg-surface text-muted";
  }
  return "border border-divider bg-divider text-muted";
}

function inputSectionLabel(step: ToolCall, t: Dictionary): string {
  if (step.name === "answer" || step.name === "reasoning" || step.name === "verify" || step.name === "revise") {
    return t.chat.sectionModel;
  }
  return t.chat.sectionInput;
}

function outputSectionLabel(step: ToolCall, t: Dictionary): string {
  if (step.name === "answer" || step.name === "verify" || step.name === "revise") {
    return t.chat.sectionUsedTokens;
  }
  if (step.name === "reasoning") return t.chat.sectionReasoning;
  return t.chat.sectionOutput;
}

/** システムの処理の入力・出力。短い値は表に、長い文章（整形の前後・要約など）は読める箱に出す。 */
export function SystemFields({ data, t }: { data: Record<string, unknown>; t: Dictionary }) {
  const rows: { k: string; v: React.ReactNode }[] = [];
  const texts: [string, string][] = [];
  for (const [k, v] of Object.entries(data)) {
    if (k === "kind") continue;
    if (typeof v === "string" && (v.length > 60 || v.includes("\n"))) texts.push([k, v]);
    else rows.push({ k: systemFieldLabel(k, t), v: systemValueLabel(k, v, t) });
  }
  return (
    <div className="space-y-2">
      {rows.length > 0 && <KeyValueGrid rows={rows} />}
      {texts.map(([k, v]) => (
        <div key={k}>
          <div className={sectionLabelCls}>{systemFieldLabel(k, t)}</div>
          <div className="max-h-64 overflow-y-auto whitespace-pre-wrap break-words rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 text-footnote leading-[1.55] text-fg-2">
            {v.trim()}
          </div>
        </div>
      ))}
    </div>
  );
}

/** システムの処理の短い値。配列は「, 」でつなぎ、内訳から確かめた数字（number_check の derived）は式にする。 */
export function systemFieldValue(
  v: unknown,
  reasons: Record<string, string> = {},
  prune: { removed: string; kept: string; values: string } = { removed: "-", kept: "+", values: "=" },
): string {
  if (!Array.isArray(v)) return String(v);
  if (!v.length) return "—";
  return v
    .map((x) => {
      if (x && typeof x === "object" && "value" in x && Array.isArray((x as { from?: unknown }).from)) {
        const d = x as { value: unknown; op?: unknown; from: unknown[] };
        return `${String(d.value)} = ${d.from.map(String).join(d.op === "diff" ? " − " : " + ")}`;
      }
      if (x && typeof x === "object" && "sentence" in x && Array.isArray((x as { removed?: unknown }).removed)) {
        // 引用の刈り込み（specs/026 T31）: 文の冒頭・外した番号・残した番号・その文の値
        // 番号は検索で振った番号（保存のときに振り直される）なので、資料の名前があれば添える
        const d = x as {
          sentence: unknown;
          removed: unknown[];
          kept?: unknown[];
          values?: unknown[];
          documents?: Record<string, unknown>;
        };
        const docs = d.documents;
        const marks = (ns: unknown[] | undefined) =>
          docs
            ? (ns ?? []).map((n) => `[${String(n)}] ${String(docs[String(n)] ?? "")}`.trim()).join("、")
            : (ns ?? []).map((n) => `[${String(n)}]`).join("");
        return `「${String(d.sentence)}」${prune.removed} ${marks(d.removed)}・${prune.kept} ${marks(d.kept)}（${prune.values}: ${(d.values ?? []).map(String).join("・")}）`;
      }
      if (x && typeof x === "object" && "question" in x && "reason" in x) {
        // 落とした候補（続けて聞く）。理由は読める名前にし、根拠の語句があれば添える（specs/028 T23）
        const d = x as { question: unknown; reason: unknown; evidence?: unknown };
        const reason = reasons[String(d.reason)] ?? String(d.reason);
        return `${String(d.question)}（${reason}${typeof d.evidence === "string" ? `: 「${d.evidence}」` : ""}）`;
      }
      if (x && typeof x === "object" && "question" in x && "evidence" in x) {
        // 残した候補と根拠の語句
        const d = x as { question: unknown; evidence: unknown };
        return `${String(d.question)}（「${String(d.evidence)}」）`;
      }
      return String(x);
    })
    .join(", ");
}

/** 決まった値（空の生成の結果・未了の確認の種類）は読める名前にする。それ以外は systemFieldValue のまま。 */
function systemValueLabel(key: string, v: unknown, t: Dictionary): string {
  const names = (t.chat.systemValues as Record<string, Record<string, string>>)[key];
  return typeof v === "string" && names?.[v] ? names[v] : systemFieldValue(v, t.chat.droppedReasons, t.chat.pruneLabels);
}

function systemFieldLabel(key: string, t: Dictionary): string {
  return (t.chat.systemFields as Record<string, string>)[key] ?? key;
}

const boxCls = "rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 text-footnote leading-[1.55] text-fg-2";

/** システムが先に行った検索の札（モデルが自分で行った検索と見分ける）。 */
function AutoBadge({ t }: { t: Dictionary }) {
  return (
    <span
      title={t.chat.bySystemHint}
      className="shrink-0 rounded-full border-[0.5px] border-divider-strong px-1.5 py-px text-mini font-medium leading-none text-muted"
    >
      {t.chat.bySystem}
    </span>
  );
}

function isBySystem(step: ToolCall): boolean {
  return step.input.by === "system";
}

/** Markdown の表を含む文章（table_query の結果）。表は表として、ほかの行は文章として出す。 */
function TableText({ text }: { text: string }) {
  const body = text.replace(/^<資料[^>]*>\n?/, "").replace(/\n?<\/資料>\s*$/, "");
  const blocks: ({ kind: "text"; lines: string[] } | { kind: "table"; rows: string[][] })[] = [];
  for (const line of body.split("\n")) {
    const isRow = line.trimStart().startsWith("|");
    const last = blocks[blocks.length - 1];
    if (isRow) {
      if (/^\s*\|[\s:|-]+\|\s*$/.test(line)) continue; // 区切り行
      const cells = line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      if (last?.kind === "table") last.rows.push(cells);
      else blocks.push({ kind: "table", rows: [cells] });
    } else if (line.trim()) {
      if (last?.kind === "text") last.lines.push(line);
      else blocks.push({ kind: "text", lines: [line] });
    }
  }
  return (
    <div className="space-y-2">
      {blocks.map((b, i) =>
        b.kind === "text" ? (
          <div key={i} className="whitespace-pre-wrap break-words text-footnote leading-[1.55] text-fg-2">
            {b.lines.join("\n")}
          </div>
        ) : (
          <DataTable key={i} rows={b.rows} />
        ),
      )}
    </div>
  );
}

/** 表（1 行目が見出し）。数の列は右寄せ。 */
function DataTable({ rows }: { rows: string[][] }) {
  return (
    <div className="overflow-x-auto rounded-control border-[0.5px] border-divider bg-code-bg">
      <table className="w-full border-collapse text-caption">
        <thead>
          <tr>
            {rows[0].map((c, j) => (
              <th key={j} className="whitespace-nowrap border-b-[0.5px] border-divider-strong px-2.5 py-1.5 text-left font-semibold text-fg">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(1).map((r, k) => (
            <tr key={k} className="border-t-[0.5px] border-divider first:border-t-0">
              {r.map((c, j) => (
                <td key={j} className={cn("px-2.5 py-1.5 text-fg-2", /^-?[\d,.]+$/.test(c) && "text-right font-mono tabular-nums")}>
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type Stats = { sum: string; avg: string; max: string; min: string };

/**
 * 表の集計の結果（specs/028 R10）。該当行の表 → 該当 n 行 / 全 m 行 → compute の列の集計、
 * ほかの列の集計は「すべての集計」（既定は閉）。構造の無い古い記録は、モデルに渡した文のまま出す。
 */
export function TableResult({ output, t }: { output: Record<string, unknown>; t: Dictionary }) {
  const { rows, columns, rows_matched: matched, rows_total: total } = output;
  if (!Array.isArray(rows) || !Array.isArray(columns) || typeof matched !== "number" || typeof total !== "number") {
    return typeof output.result === "string" ? <TableText text={output.result} /> : null;
  }
  const label = typeof output.compute_label === "string" ? output.compute_label : null;
  const aggs = (output.aggregates ?? {}) as Record<string, Stats>;
  const main = label ? aggs[label] : undefined;
  const others = Object.entries(aggs).filter(([k]) => k !== label);
  const statRows = (a: Stats) => [
    { k: t.chat.aggSum, v: a.sum },
    { k: t.chat.aggAvg, v: a.avg },
    { k: t.chat.aggMax, v: a.max },
    { k: t.chat.aggMin, v: a.min },
  ];
  return (
    <div className="space-y-2">
      {rows.length > 0 && <DataTable rows={[columns.map(String), ...(rows as unknown[][]).map((r) => r.map(String))]} />}
      <div className="text-caption text-muted">
        {t.chat.tableMatched.replace("{n}", String(matched)).replace("{m}", String(total))}
      </div>
      {Array.isArray(output.notes) && output.notes.length > 0 && (
        <div className="text-caption text-muted">
          <span className={sectionLabelCls}>{t.chat.tableNotes}</span>
          {(output.notes as unknown[]).map((n, i) => (
            <p key={i}>{String(n)}</p>
          ))}
        </div>
      )}
      {label && output.compute_value !== undefined && (
        <KeyValueGrid rows={[{ k: label, v: output.compute_value === null ? "—" : String(output.compute_value) }]} />
      )}
      {label && main && (
        <div>
          <div className={sectionLabelCls}>{label}</div>
          <KeyValueGrid rows={statRows(main)} />
        </div>
      )}
      {others.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-caption text-muted outline-none hover:text-fg-2 focus-visible:ring-2 focus-visible:ring-accent/50">
            {t.chat.tableAllAggregates}
          </summary>
          <div className="mt-2">
            <DataTable
              rows={[
                [t.chat.tableColumn, t.chat.aggSum, t.chat.aggAvg, t.chat.aggMax, t.chat.aggMin],
                ...others.map(([k, a]) => [k, a.sum, a.avg, a.max, a.min]),
              ]}
            />
          </div>
        </details>
      )}
    </div>
  );
}

function ToolInputBlock({ step, t }: { step: ToolCall; t: Dictionary }) {
  if ((step.name === "reasoning" || step.name === "answer") && typeof step.input.model === "string") {
    return <ModelBlock model={step.input.model} />;
  }
  if ((step.name === "verify" || step.name === "revise") && typeof step.input.model === "string") {
    return <ModelBlock model={step.input.model} />;
  }
  if (step.name === "system") return <SystemFields data={step.input} t={t} />;
  if (step.name === "understand" && typeof step.input.question === "string") {
    return <div className={cn(boxCls, "whitespace-pre-wrap break-words")}>{step.input.question}</div>;
  }
  if (step.name === "table_query") {
    const code = (v: unknown) => <code className="font-mono text-caption text-fg">{String(v)}</code>;
    const rows = [
      { k: t.chat.tableSource, v: `[${String(step.input.source ?? "")}]` },
      { k: t.chat.tableWhere, v: step.input.where ? code(step.input.where) : t.chat.tableAll },
    ];
    if (step.input.compute) rows.push({ k: t.chat.tableCompute, v: code(step.input.compute) });
    return <KeyValueGrid rows={rows} />;
  }
  if (step.name === "review") {
    // 差し戻した下書きを丸ごと見せる（回答の欄からは消えるが、記録には残す）
    const rows: { k: string; v: React.ReactNode }[] = [];
    if (typeof step.input.trigger === "string") rows.push({ k: t.chat.reviewTrigger, v: `「${step.input.trigger}」` });
    if (typeof step.input.searches === "number") rows.push({ k: t.chat.reviewSearches, v: String(step.input.searches) });
    return (
      <div className="space-y-2">
        {rows.length > 0 && <KeyValueGrid rows={rows} />}
        {typeof step.input.draft === "string" && (
          <div>
            <div className={sectionLabelCls}>{t.chat.reviewDraft}</div>
            <div className="max-h-64 overflow-y-auto whitespace-pre-wrap break-words rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 text-footnote leading-[1.55] text-fg-2">
              {step.input.draft.trim()}
            </div>
          </div>
        )}
      </div>
    );
  }
  if (step.name === "retrieve" && typeof step.input.query === "string") {
    return (
      <div className="rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5">
        <div className="mb-1 font-mono text-mini uppercase tracking-[0.06em] text-muted-2">query</div>
        <div className="text-footnote leading-[1.5] text-fg">{step.input.query}</div>
      </div>
    );
  }
  if (step.name === "fetch_document") {
    const ref = step.input.ref;
    const document = step.input.document;
    return (
      <div className="space-y-[3px] rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 font-mono text-caption leading-[1.6] text-fg-2">
        {ref != null && (
          <div>
            <span className="text-muted-2">{t.chat.sourceLabel}</span>
            <span className="text-fg">[{String(ref)}]</span>
          </div>
        )}
        {document != null && (
          <div>
            <span className="text-muted-2">{t.chat.documentLabel}</span>
            <span className="text-fg">{String(document)}</span>
          </div>
        )}
      </div>
    );
  }
  if (step.name === "vector_search" || step.name === "bm25_search") {
    const rows: { k: string; v: React.ReactNode }[] = [];
    if (typeof step.input.mode === "string") rows.push({ k: "mode", v: step.input.mode });
    return (
      <div className="space-y-2">
        {rows.length > 0 && <KeyValueGrid rows={rows} />}
        {typeof step.input.query === "string" && (
          <div className="rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5">
            <div className="mb-1 font-mono text-mini uppercase tracking-[0.06em] text-muted-2">query</div>
            <div title={step.input.query} className="line-clamp-3 break-words text-footnote leading-[1.5] text-fg [overflow-wrap:anywhere]">{step.input.query}</div>
          </div>
        )}
      </div>
    );
  }
  if (step.name === "rerank") {
    const rows: { k: string; v: React.ReactNode }[] = [];
    if (step.input.model != null) rows.push({ k: "model", v: String(step.input.model) });
    if (step.input.top_n != null) rows.push({ k: "top_n", v: String(step.input.top_n) });
    if (rows.length) return <KeyValueGrid rows={rows} />;
  }
  if (step.name === "embed" && step.input.model != null) {
    return <KeyValueGrid rows={[{ k: "model", v: String(step.input.model) }]} />;
  }
  return <pre className={preCls}>{JSON.stringify(step.input, null, 2)}</pre>;
}

function VerifyDetailRow({ detail, index, t }: { detail: VerifyDetail; index: number; t: Dictionary }) {
  const citedNums = Array.isArray(detail.citedNums) ? detail.citedNums : [];
  const verdict = detail.verdict === "supported" || detail.verdict === "unsupported" || detail.verdict === "not_a_claim" || detail.verdict === "unverified"
    ? detail.verdict
    : "not_a_claim";
  return (
    <div className={cn("px-3 py-2.5", index > 0 && "border-t-[0.5px] border-divider")}>
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className={cn(
          "rounded-full px-2 py-px text-mini font-semibold",
          verifyVerdictChipClass(verdict),
        )}>
          {verifyVerdictLabel(verdict, t)}
        </span>
        {citedNums.length > 0 && (
          <span className="font-mono text-mini text-muted-2">
            {t.chat.verifyCitations}: {citedNums.map((n) => `[${n}]`).join(" ")}
          </span>
        )}
      </div>
      <div className="mt-1 whitespace-pre-wrap break-words text-footnote leading-[1.5] text-fg-2">
        {detail.text}
      </div>
      {detail.reason && (
        <div className="mt-1 whitespace-pre-wrap break-words font-mono text-mini leading-[1.5] text-muted-2">
          {t.chat.verifyReason}: {detail.reason}
        </div>
      )}
    </div>
  );
}

function ToolOutputBlock({ step, t }: { step: ToolCall; t: Dictionary }) {
  const output = step.output;
  if (!output) return null;

  if (step.name === "answer") {
    return hasTokenUsage(output) ? <KeyValueGrid rows={tokenRows(output, t)} /> : null;
  }

  if (step.name === "read_image") {
    // 画像から読み取った文章（失敗時は理由）
    const text = typeof output.description === "string" ? output.description : typeof output.error === "string" ? output.error : "";
    return text ? <pre className={preCls}>{text}</pre> : null;
  }

  if (step.name === "reasoning") {
    return (
      typeof output.reasoning === "string" && output.reasoning.length > 0
        ? <pre className={preCls}>{output.reasoning}</pre>
        : null
    );
  }

  if (step.name === "rerank" && Array.isArray(output.selected)) {
    return (
      <div className="flex flex-col gap-[5px] py-1">
        {(output.selected as RerankHit[]).map((s) => (
          <div
            key={s.id}
            className="grid grid-cols-[80px_42px_1fr] items-center gap-2.5 text-caption max-md:grid-cols-[90px_38px_1fr] max-md:gap-2"
          >
            <div className="h-[5px] overflow-hidden rounded-full bg-divider">
              <span className="block h-full rounded-full bg-accent" style={{ width: `${s.score * 100}%` }} />
            </div>
            <span className="font-mono text-caption font-semibold text-accent">{s.score.toFixed(2)}</span>
            <span className="truncate text-fg-2">{s.title}</span>
          </div>
        ))}
      </div>
    );
  }
  if ((step.name === "vector_search" || step.name === "bm25_search") && Array.isArray(output.hits)) {
    const hits = output.hits as CandidateHit[];
    if (hits.length === 0) {
      if (output.fallback) {
        const terms = Array.isArray(output.terms)
          ? (output.terms as unknown[]).map(String)
          : String(step.input.query ?? "").split(/\s+/).filter(Boolean);
        return (
          <div className="flex items-start gap-1.5 rounded-control bg-surface-2 px-2.5 py-2 text-caption leading-[1.6] text-fg-2">
            <Icon name="info" size={12} className="mt-[3px] shrink-0 text-muted" />
            <span>
              {interpolate(output.fallback === "codes" ? t.chat.keywordRelax : t.chat.keywordFallback, {
                terms: terms.map((x) => `「${x}」`).join(""),
              })}
            </span>
          </div>
        );
      }
      return <div className="px-1 py-1 text-caption text-muted">{t.chat.noCandidates}</div>;
    }
    // スコアは非負前提（dense=cosine, sparse=BM25/dot）。リスト内最大値でバー幅を正規化。
    const max = Math.max(...hits.map((h) => h.score), 1e-9);
    return (
      <div className="flex max-h-72 flex-col gap-[5px] overflow-y-auto py-1">
        {hits.map((h, i) => (
          <div
            key={i}
            className="grid grid-cols-[64px_42px_1fr] items-center gap-2.5 text-caption max-md:grid-cols-[54px_38px_1fr] max-md:gap-2"
          >
            <div className="h-[5px] overflow-hidden rounded-full bg-divider">
              <span className="block h-full rounded-full bg-accent" style={{ width: `${Math.max(4, (h.score / max) * 100)}%` }} />
            </div>
            <span className="font-mono text-caption font-semibold text-accent">{h.score.toFixed(2)}</span>
            <span className="truncate text-fg-2">
              <span className="text-fg">{h.title}</span>
              {h.heading && <span className="text-muted-2"> — {h.heading}</span>}
            </span>
          </div>
        ))}
      </div>
    );
  }
  if (step.name === "embed") {
    return <KeyValueGrid rows={[{ k: "dims", v: String(output.dims ?? "—") }]} />;
  }
  if (step.name === "expand") {
    const expanded = Array.isArray(output.expanded) ? (output.expanded as ExpandedHit[]) : [];
    if (expanded.length === 0) {
      return <KeyValueGrid rows={[{ k: t.chat.expandCount, v: String(output.count ?? 0) }]} />;
    }
    return (
      <div className="flex flex-col gap-2">
        <KeyValueGrid rows={[{ k: t.chat.expandCount, v: String(output.count ?? expanded.length) }]} />
        <div className="overflow-hidden rounded-control border-[0.5px] border-divider bg-code-bg">
          {expanded.map((h, i) => (
            <div key={`${h.id}-${i}`} className={cn("px-3 py-2.5", i > 0 && "border-t-[0.5px] border-divider")}>
              <div className="flex min-w-0 items-center gap-2">
                <span className="font-mono text-caption font-semibold tabular-nums text-accent">{h.score.toFixed(2)}</span>
                <span className="min-w-0 flex-1 truncate text-footnote font-medium text-fg">{h.title}</span>
                <span className="shrink-0 font-mono text-mini text-muted-2">p.{h.page}</span>
                <span className="shrink-0 font-mono text-mini text-muted-2">{h.expandedChars}ch</span>
              </div>
              {h.heading && <div className="mt-0.5 truncate font-mono text-mini text-muted-2">{h.heading}</div>}
              {h.preview && <div className="mt-1 line-clamp-2 whitespace-pre-wrap text-caption leading-[1.5] text-fg-2">{h.preview}</div>}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (step.name === "grade") {
    const candidates = Array.isArray(output.candidates) ? (output.candidates as GradeCandidate[]) : [];
    if (candidates.length === 0) return <pre className={preCls}>{JSON.stringify(output, null, 2)}</pre>;
    return (
      <div className="flex flex-col gap-2">
        <KeyValueGrid rows={[
          { k: "kept", v: `${String(output.kept ?? 0)} / ${String(output.total ?? candidates.length)}` },
          { k: "retry", v: output.needRetry ? "yes" : "no" },
        ]} />
        <div className="overflow-hidden rounded-control border-[0.5px] border-divider bg-code-bg">
          {candidates.map((c, i) => (
            <div key={`${c.chunkId}-${i}`} className={cn("grid grid-cols-[58px_42px_1fr] items-start gap-2.5 px-3 py-2.5 text-caption", i > 0 && "border-t-[0.5px] border-divider")}>
              <span className={cn("rounded-full px-2 py-px text-center text-mini font-semibold", c.kept ? "bg-accent-soft text-accent" : "bg-divider text-muted")}>
                {c.kept ? "kept" : "skip"}
              </span>
              <span className="font-mono text-caption font-semibold tabular-nums text-accent">{c.score.toFixed(2)}</span>
              <span className="min-w-0">
                <span className="block truncate text-fg">{c.title}</span>
                {c.heading && <span className="block truncate font-mono text-mini text-muted-2">{c.heading}</span>}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if ((step.name === "retrieve" || step.name === "fetch_document") && typeof output.result === "string") {
    const hits = parseRetrieveHits(output.result);
    if (hits.length) {
      return (
        <div className="overflow-hidden rounded-control border-[0.5px] border-divider bg-code-bg">
          {hits.map((h, i) => (
            <div
              key={`${h.n}-${i}`}
              className={cn(
                "grid grid-cols-[28px_1fr] gap-2 px-3 py-2.5",
                i > 0 && "border-t-[0.5px] border-divider",
              )}
            >
              <span className="pt-px font-mono text-caption font-semibold text-accent">[{h.n}]</span>
              <div className="min-w-0">
                <div className="truncate text-footnote font-medium text-fg">{h.title}</div>
                <div className="truncate font-mono text-mini text-muted-2">{h.heading}</div>
                {h.snippet && (
                  <div className="mt-1 line-clamp-3 whitespace-pre-wrap text-caption leading-[1.5] text-fg-2">
                    {h.snippet}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      );
    }
    // パースに失敗（"該当する資料は見つかりませんでした。" 等）した場合は本文をそのまま見せる。
    return (
      <div className="rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 text-footnote leading-[1.55] text-fg-2">
        {output.result}
      </div>
    );
  }

  if (step.name === "verify") {
    const claims = Array.isArray(output.claims) ? (output.claims as string[]) : [];
    const details = Array.isArray(output.details) ? (output.details as VerifyDetail[]) : [];
    const verifyError = typeof output.verifyError === "string" ? output.verifyError : "";
    const message = verifyError ? t.chat.verifyFailed : output.checkableClaims === 0 ? t.chat.noCheckableClaims : t.chat.allGrounded;
    const detailBlock = details.length > 0 && (
      <div>
        <div className={sectionLabelCls}>{t.chat.sectionVerifyDetails}</div>
        <div className="overflow-hidden rounded-control border-[0.5px] border-divider bg-code-bg">
          {details.slice(0, VERIFY_DETAIL_MAX).map((detail, i) => (
            <VerifyDetailRow key={`${detail.verdict}-${i}`} detail={detail} index={i} t={t} />
          ))}
          {details.length > VERIFY_DETAIL_MAX && (
            <div className="border-t-[0.5px] border-divider px-3 py-2.5 text-caption text-muted-2">
              {interpolate(t.chat.moreItems, { n: details.length - VERIFY_DETAIL_MAX })}
            </div>
          )}
        </div>
      </div>
    );
    if (claims.length === 0) {
      return (
        <div className="flex flex-col gap-2">
          {hasTokenUsage(output) && <KeyValueGrid rows={tokenRows(output, t)} />}
          <div className="rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 text-footnote leading-[1.55] text-fg-2">
            {message}
            {verifyError && <div className="mt-1 font-mono text-mini text-muted-2">{verifyError}</div>}
          </div>
          {detailBlock}
        </div>
      );
    }
    return (
      <div className="flex flex-col gap-2">
        {hasTokenUsage(output) && <KeyValueGrid rows={tokenRows(output, t)} />}
        <ul className="flex flex-col gap-1.5 rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5">
          {claims.map((c, i) => (
            <li key={i} className="grid grid-cols-[14px_1fr] gap-2 text-footnote leading-[1.5] text-fg-2">
              <span className="pt-px text-center font-mono text-caption font-semibold text-danger">!</span>
              <span className="min-w-0 whitespace-pre-wrap break-words">{c}</span>
            </li>
          ))}
        </ul>
        {detailBlock}
      </div>
    );
  }

  if (step.name === "revise") {
    return (
      <div className="flex flex-col gap-2">
        {hasTokenUsage(output) && <KeyValueGrid rows={tokenRows(output, t)} />}
        {typeof output.draft === "string" && (
          <div>
            <div className={sectionLabelCls}>{t.chat.sectionDraft}</div>
            <div className="whitespace-pre-wrap break-words rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 text-footnote leading-[1.55] text-muted">
              {output.draft}
            </div>
          </div>
        )}
        {typeof output.revised === "string" && (
          <div>
            <div className={sectionLabelCls}>{t.chat.sectionRevised}</div>
            <div className="whitespace-pre-wrap break-words rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 text-footnote leading-[1.55] text-fg-2">
              {output.revised}
            </div>
          </div>
        )}
      </div>
    );
  }

  if (step.name === "system") return <SystemFields data={output} t={t} />;

  if (step.name === "understand") {
    const queries = Array.isArray(output.queries) ? (output.queries as unknown[]).map(String) : [];
    const chip = "rounded-full border-[0.5px] border-divider-strong bg-surface px-2 py-0.5 text-caption text-fg-2";
    return (
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={chip}>{output.kind === "chat" ? t.chat.understandKindChat : t.chat.understandKindDocs}</span>
          {output.table === true && <span className={chip}>{t.chat.understandTable}</span>}
        </div>
        {queries.length > 0 && (
          <div>
            <div className={sectionLabelCls}>{t.chat.understandQueries}</div>
            <ol className="m-0 list-none space-y-1 p-0">
              {queries.map((q, i) => (
                <li key={i} className={cn(boxCls, "flex gap-2 py-1.5")}>
                  <span className="font-mono text-caption text-muted-2">{i + 1}</span>
                  <span className="min-w-0 break-words text-fg">{q}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
        {typeof output.error === "string" && (
          <div className="text-caption text-muted">
            {t.chat.understandError}（{output.error}）
          </div>
        )}
      </div>
    );
  }

  if (step.name === "table_query" && typeof output.result === "string") {
    return <TableResult output={output} t={t} />;
  }

  if (step.name === "review" && typeof output.note === "string") {
    const next = Array.isArray(output.next_tools) ? (output.next_tools as unknown[]).map(String) : [];
    return (
      <div className="space-y-2">
        <div>
          <div className={sectionLabelCls}>{t.chat.reviewNote}</div>
          <div className="whitespace-pre-wrap break-words rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 text-footnote leading-[1.55] text-fg-2">
            {output.note}
          </div>
        </div>
        <KeyValueGrid rows={[{ k: t.chat.reviewNext, v: next.length ? next.join("・") : t.chat.reviewRewrote }]} />
        {typeof output.error === "string" && <pre className={preCls}>{output.error}</pre>}
      </div>
    );
  }

  // work_calendar は整形済みの事実テキスト（{result:"..."}）。そのまま可読表示する。
  if (step.name === "work_calendar" && typeof output.result === "string") {
    return (
      <div className="whitespace-pre-wrap break-words rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 text-footnote leading-[1.55] text-fg-2">
        {output.result}
      </div>
    );
  }

  return <pre className={preCls}>{JSON.stringify(output, null, 2)}</pre>;
}

function ToolStepCard({ step, expanded, onToggle, t, hasChildren = false }: { step: ToolCall; expanded: boolean; onToggle: () => void; t: Dictionary; hasChildren?: boolean }) {
  // 子（検索の明細など）を持つ段階は、開閉で子を出す。自分の入力・出力は子と同じ内容なので出さない
  const expandable = hasChildren || isExpandable(step);
  const showInput = !hasChildren && hasInputData(step.input);
  const showOutput = !hasChildren && step.output != null;
  return (
    <div className="border-b-[0.5px] border-divider last:border-b-0">
      <button
        type="button"
        onClick={expandable ? onToggle : undefined}
        aria-expanded={expandable ? expanded : undefined}
        className={cn(
          "grid w-full grid-cols-[16px_16px_auto_auto_1fr_auto_16px] items-center gap-2.5 border-0 px-3.5 py-[9px] text-left text-footnote text-fg",
          "max-md:grid-cols-[16px_16px_1fr_auto_16px] max-md:gap-2 max-md:px-3 max-md:text-footnote",
          expandable ? "cursor-pointer hover:bg-surface" : "cursor-default",
          step.status === "running" && "bg-accent-soft",
        )}
      >
        <StatusIcon status={step.status} t={t} name={step.name} />
        <span className="grid place-items-center text-accent">
          <svg viewBox="0 0 16 16" width="13" height="13">
            {TOOL_ICONS[step.name]}
          </svg>
        </span>
        {/* 日本語の名前を主に、ツール名は小さく添える */}
        <span className="inline-flex min-w-0 items-center gap-1.5 text-footnote font-semibold text-fg">
          <span className="truncate">{step.label || step.name}</span>
          {isBySystem(step) && <AutoBadge t={t} />}
        </span>
        <span className="font-mono text-mini text-muted-2 max-md:hidden">{step.label ? step.name : ""}</span>
        <span className="min-w-0 truncate text-footnote text-muted max-md:hidden">{step.summary}</span>
        <span className="font-mono text-caption tabular-nums text-muted">{stepDurationLabel(step)}</span>
        {expandable ? (
          <span className={cn("text-muted transition-transform", expanded && "rotate-180")}>
            <svg viewBox="0 0 16 16" width="11" height="11">
              <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        ) : (
          <span aria-hidden className="block h-[11px] w-[11px]" />
        )}
      </button>
      {expandable && expanded && !hasChildren && (
        <div className="flex flex-col gap-2.5 border-t-[0.5px] border-dashed border-divider bg-surface px-3.5 pb-3.5 pl-10 pt-2 max-md:pl-3.5">
          {showInput && (
            <div>
              <div className={sectionLabelCls}>{inputSectionLabel(step, t)}</div>
              <ToolInputBlock step={step} t={t} />
            </div>
          )}
          {showOutput && (
            <div>
              <div className={sectionLabelCls}>{outputSectionLabel(step, t)}</div>
              <ToolOutputBlock step={step} t={t} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ToolStepTimeline({ step, expanded, onToggle, isLast, t, hasChildren = false }: { step: ToolCall; expanded: boolean; onToggle: () => void; isLast: boolean; t: Dictionary; hasChildren?: boolean }) {
  const expandable = hasChildren || isExpandable(step);
  const showInput = !hasChildren && hasInputData(step.input);
  const showOutput = !hasChildren && step.output != null;
  return (
    <div className="grid grid-cols-[22px_1fr]">
      <div className="grid grid-rows-[auto_1fr] items-start justify-items-center pt-0.5">
        <div className="grid h-[22px] w-[22px] place-items-center bg-surface-2">
          <StatusIcon status={step.status} t={t} name={step.name} />
        </div>
        {!isLast && <div className="min-h-4 w-[1.5px] flex-1 bg-divider-strong" />}
      </div>
      <div className="min-w-0 pb-3 pl-1">
        <button
          type="button"
          onClick={expandable ? onToggle : undefined}
          aria-expanded={expandable ? expanded : undefined}
          className={cn(
            "flex w-full items-center gap-2.5 border-0 bg-transparent py-0.5 text-left text-fg",
            expandable ? "cursor-pointer" : "cursor-default",
          )}
        >
          <span className="font-mono text-caption font-semibold text-fg">{step.name}</span>
          {isBySystem(step) && <AutoBadge t={t} />}
          <span className="min-w-0 flex-1 truncate text-footnote text-muted">{step.summary}</span>
          <span className="font-mono text-caption tabular-nums text-muted">{stepDurationLabel(step)}</span>
        </button>
        {expandable && expanded && !hasChildren && (
          <div className="flex flex-col gap-2 pt-2">
            {showInput && (
              <div>
                <div className={sectionLabelCls}>{inputSectionLabel(step, t)}</div>
                <ToolInputBlock step={step} t={t} />
              </div>
            )}
            {showOutput && (
              <div>
                <div className={sectionLabelCls}>{outputSectionLabel(step, t)}</div>
                <ToolOutputBlock step={step} t={t} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function ToolStepLog({ steps, dict }: { steps: ToolCall[]; dict: Dictionary }) {
  const lines: { t: number; name: string; msg: string; kind: string }[] = [];
  let t = 0;
  steps.forEach((s) => {
    const start = t;
    const logName = (s.parentId ? "› " : "") + s.name;
    lines.push({ t: start, name: logName, msg: "started", kind: "start" });
    const keys = Object.keys(s.input);
    if (keys.length) {
      const k = keys[0];
      const v = s.input[k];
      lines.push({ t: start, name: logName, msg: `${k}: ${typeof v === "string" ? `"${v}"` : JSON.stringify(v)}`, kind: "param" });
    }
    if (s.status === "done") {
      lines.push({ t: start + s.durationMs, name: logName, msg: `done in ${formatMs(s.durationMs)} · ${s.summary}`, kind: "done" });
      const out = (s.output ?? {}) as Record<string, unknown>;
      const dt = start + s.durationMs;
      if ((s.name === "vector_search" || s.name === "bm25_search") && Array.isArray(out.hits)) {
        const hits = out.hits as { title: string; heading: string; score: number }[];
        hits.slice(0, LOG_DETAIL_MAX).forEach((h) =>
          lines.push({ t: dt, name: "", msg: `${h.score.toFixed(2)}  ${h.title}${h.heading ? ` — ${h.heading}` : ""}`, kind: "detail" }));
        if (hits.length > LOG_DETAIL_MAX)
          lines.push({ t: dt, name: "", msg: interpolate(dict.chat.moreItems, { n: hits.length - LOG_DETAIL_MAX }), kind: "detail" });
      } else if (s.name === "rerank" && Array.isArray(out.selected)) {
        const sel = out.selected as { score: number; title: string }[];
        sel.slice(0, LOG_DETAIL_MAX).forEach((h) =>
          lines.push({ t: dt, name: "", msg: `${h.score.toFixed(2)}  ${h.title}`, kind: "detail" }));
        if (sel.length > LOG_DETAIL_MAX)
          lines.push({ t: dt, name: "", msg: interpolate(dict.chat.moreItems, { n: sel.length - LOG_DETAIL_MAX }), kind: "detail" });
      }
      t = start + s.durationMs;
    } else if (s.status === "running") {
      lines.push({ t: start + (s.durationMs || 0), name: logName, msg: "streaming…", kind: "running" });
    }
  });
  const fmtT = (ms: number) => `+${Math.floor(ms / 1000).toString().padStart(2, "0")}.${(ms % 1000).toString().padStart(3, "0").slice(0, 3)}`;

  return (
    <div className="max-h-80 overflow-y-auto bg-code-bg px-4 pb-3.5 pt-2.5 font-mono text-caption leading-[1.65] text-fg-2 max-md:max-h-[260px] max-md:px-3 max-md:text-mini">
      {lines.map((l, i) => (
        <div key={i} className="flex gap-3 py-px">
          <span className="shrink-0 text-muted-2">{fmtT(l.t)}</span>
          <span className={cn("min-w-[110px] shrink-0 max-md:min-w-[90px]", l.kind === "done" ? "text-accent" : "text-accent")}>{l.name}</span>
          <span
            className={cn(
              "min-w-0 flex-1 break-words",
              l.kind === "done" ? "text-fg" : l.kind === "param" ? "text-muted" : l.kind === "running" ? "text-accent" : l.kind === "detail" ? "text-muted-2" : "text-fg-2",
            )}
          >
            {l.msg}
          </span>
        </div>
      ))}
    </div>
  );
}

interface Props {
  steps: ToolCall[];
  variant: ToolView;
  expandedMap: Record<string, boolean>;
  onToggleStep: (id: string) => void;
  /** 「システムの処理」を最初から開いておく（管理者が報告を読むとき。specs/028 R14） */
  systemOpen?: boolean;
}

/** フラットな steps を「ルート(parentId なし)」と「子(parentId 別)」に分ける。 */
function groupSteps(steps: ToolCall[]): { roots: ToolCall[]; childrenOf: Map<string, ToolCall[]> } {
  const roots: ToolCall[] = [];
  const childrenOf = new Map<string, ToolCall[]>();
  for (const s of steps) {
    if (s.parentId) {
      const arr = childrenOf.get(s.parentId) ?? [];
      arr.push(s);
      childrenOf.set(s.parentId, arr);
    } else {
      roots.push(s);
    }
  }
  return { roots, childrenOf };
}

/** 子サブステップの行。詳細があれば展開可能。card / timeline 共通。 */
function SubStepRow({ step, expanded, onToggle, t }: { step: ToolCall; expanded: boolean; onToggle: () => void; t: Dictionary }) {
  const expandable = isExpandable(step);
  const hits = searchHits(step);
  const showInput = hasInputData(step.input);
  const showOutput = step.output != null;
  return (
    <div>
      <button
        type="button"
        onClick={expandable ? onToggle : undefined}
        aria-expanded={expandable ? expanded : undefined}
        className={cn(
          "flex w-full items-center gap-2.5 border-0 bg-transparent py-[3px] text-left text-caption text-fg-2",
          expandable ? "cursor-pointer hover:text-fg" : "cursor-default",
        )}
      >
        <StatusIcon status={step.status} t={t} name={step.name} />
        <span className="grid place-items-center text-muted-2">
          <svg viewBox="0 0 16 16" width="12" height="12">{TOOL_ICONS[step.name]}</svg>
        </span>
        <span className="truncate text-caption font-semibold text-fg-2">{step.label || step.name}</span>
        <span className="font-mono text-mini text-muted-2 max-md:hidden">{step.label ? step.name : ""}</span>
        <span className="min-w-0 flex-1 truncate text-muted">{step.summary}</span>
        <span className="font-mono text-mini tabular-nums text-muted-2">{stepDurationLabel(step)}</span>
        {expandable ? (
          <span className={cn("text-muted-2 transition-transform", expanded && "rotate-180")}>
            <svg viewBox="0 0 16 16" width="10" height="10">
              <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        ) : (
          <span aria-hidden className="block h-[10px] w-[10px]" />
        )}
      </button>
      {expandable && expanded && hits && (
        <div className="pb-2 pl-[26px] pt-1">
          <SearchDetail step={step} hits={hits} />
        </div>
      )}
      {expandable && expanded && !hits && (
        <div className="flex flex-col gap-2 pb-2 pl-[26px] pt-1">
          {showInput && (
            <div>
              <div className={sectionLabelCls}>{inputSectionLabel(step, t)}</div>
              <ToolInputBlock step={step} t={t} />
            </div>
          )}
          {showOutput && (
            <div>
              <div className={sectionLabelCls}>{outputSectionLabel(step, t)}</div>
              <ToolOutputBlock step={step} t={t} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SubSteps({ steps, expandedMap, onToggleStep, t }: {
  steps: ToolCall[] | undefined;
  expandedMap: Record<string, boolean>;
  onToggleStep: (id: string) => void;
  t: Dictionary;
}) {
  if (!steps || steps.length === 0) return null;
  // 親（資料を検索）の中身が検索 1 回だけなら、同じことを 2 段で言わず、明細をそのまま出す
  const only = steps.length === 1 ? steps[0] : null;
  const onlyHits = only ? searchHits(only) : null;
  if (only && onlyHits) return <SearchDetail step={only} hits={onlyHits} />;
  return (
    <div className="flex flex-col gap-px border-l-[1.5px] border-divider pl-3 ml-[7px]">
      {steps.map((s) => (
        <SubStepRow key={s.id} step={s} expanded={!!expandedMap[s.id]} onToggle={() => onToggleStep(s.id)} t={t} />
      ))}
    </div>
  );
}

/**
 * システムの処理（引用の整形・ツールの必須化・回数の上限・前のターンの省略・会話の要約）を 1 組に畳む。
 * 記録には全部残すが、エージェントが自分で行った段階（検索・読む・計算・見直し）の流れを邪魔しないよう、
 * 末尾に件数だけを出し、開くと 1 件 1 行、さらに開くと中身が見える（3 段で深くなる）。
 */
function SystemGroup({ steps, expandedMap, onToggleStep, t, defaultOpen = false }: {
  steps: ToolCall[];
  expandedMap: Record<string, boolean>;
  onToggleStep: (id: string) => void;
  t: Dictionary;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (steps.length === 0) return null;
  return (
    <div className="border-t-[0.5px] border-divider">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-2.5 border-0 bg-transparent px-3.5 py-2 text-left text-caption text-muted outline-none hover:text-fg-2 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/50 max-md:px-3"
      >
        <span className="grid place-items-center text-muted-2">
          <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden>{TOOL_ICONS.system}</svg>
        </span>
        <span className="shrink-0 font-medium">{t.chat.systemGroup}</span>
        <span className="nums shrink-0 text-muted-2">{interpolate(t.chat.systemCount, { n: String(steps.length) })}</span>
        {/* 畳んでいる間は何をしたかを名前だけ並べる */}
        {!open && <span className="min-w-0 flex-1 truncate text-muted-2 max-md:hidden">{steps.map((s) => s.label).join("・")}</span>}
        <span className={cn("ml-auto text-muted-2 transition-transform", open && "rotate-180")}>
          <svg viewBox="0 0 16 16" width="10" height="10" aria-hidden>
            <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </button>
      {open && (
        <div className="animate-fade-up px-3.5 pb-2 motion-reduce:animate-none max-md:px-3">
          <div className="ml-[5px] flex flex-col gap-px border-l-[1.5px] border-divider pl-3">
            {steps.map((s) => (
              <SubStepRow key={s.id} step={s} expanded={!!expandedMap[s.id]} onToggle={() => onToggleStep(s.id)} t={t} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function ToolSteps({ steps, variant, expandedMap, onToggleStep, systemOpen }: Props) {
  const { t } = useT();
  // 生の記録（log）は全部を時刻順に出す。ほかは、システムの処理を末尾の 1 組に畳む
  if (variant === "log") return <ToolStepLog steps={steps} dict={t} />;

  const system = steps.filter((s) => s.name === "system" && !s.parentId);
  const { roots, childrenOf } = groupSteps(steps.filter((s) => !system.includes(s)));

  if (variant === "timeline") {
    return (
      <div className="px-3.5 pb-3 pt-2 max-md:px-3">
        {roots.map((s, i) => (
          <div key={s.id}>
            <ToolStepTimeline step={s} expanded={!!expandedMap[s.id]} onToggle={() => onToggleStep(s.id)} isLast={i === roots.length - 1} t={t} hasChildren={childrenOf.has(s.id)} />
            {childrenOf.has(s.id) && expandedMap[s.id] && (
              <div className="mb-2 ml-[22px] animate-fade-up pl-1 motion-reduce:animate-none">
                <SubSteps steps={childrenOf.get(s.id)} expandedMap={expandedMap} onToggleStep={onToggleStep} t={t} />
              </div>
            )}
          </div>
        ))}
        <SystemGroup steps={system} expandedMap={expandedMap} onToggleStep={onToggleStep} t={t} defaultOpen={systemOpen} />
      </div>
    );
  }
  return (
    <div className="flex flex-col">
      {roots.map((s) => (
        <div key={s.id}>
          <ToolStepCard step={s} expanded={!!expandedMap[s.id]} onToggle={() => onToggleStep(s.id)} t={t} hasChildren={childrenOf.has(s.id)} />
          {childrenOf.has(s.id) && expandedMap[s.id] && (
            <div className="animate-fade-up border-b-[0.5px] border-divider bg-surface px-3.5 py-2 pl-10 motion-reduce:animate-none max-md:pl-6">
              <SubSteps steps={childrenOf.get(s.id)} expandedMap={expandedMap} onToggleStep={onToggleStep} t={t} />
            </div>
          )}
        </div>
      ))}
      <SystemGroup steps={system} expandedMap={expandedMap} onToggleStep={onToggleStep} t={t} defaultOpen={systemOpen} />
    </div>
  );
}
