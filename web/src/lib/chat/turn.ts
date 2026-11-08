/** run のイベント・保存済みメッセージを、旧版コンポーネントの view model（Turn）に写す（specs/005-agent D3）。
 *
 * サーバの型は OpenAPI から生成したもの。コンポーネントはグラフのノード名に依存せず、
 * ここで旧版の ToolName（retrieve・fetch_document・vector_search など）に合わせる。
 */
import type { components } from "@/lib/api/schema";
import type { TurnFeedback } from "@/lib/feedback-types";
import type { CitationMap, Source, ToolCall, ToolName, Turn } from "@/lib/types";

type S = components["schemas"];
export type RunEvent = S["RunEvent"];
export type ApiStep = S["Step"];
export type ApiSource = S["SourceView"];
export type ApiMessage = S["MessageOut"];
export type ApiCitationMap = Record<string, S["CitationRef"]>;

const DOC_TOOLS = new Set(["list_documents", "get_outline", "read_section"]);

/** サーバのステップ名を旧版の表示種別に写す。 */
function viewName(step: ApiStep): ToolName {
  if (step.name === "search" || step.name === "keyword_search") return "retrieve";
  if (DOC_TOOLS.has(step.name)) return "fetch_document";
  if (step.name === "retrieve") return step.input?.mode === "keyword" ? "bm25_search" : "vector_search";
  if (step.name === "rewrite_query") return "rewrite_query";
  return step.name as ToolName;
}

function viewInput(step: ApiStep): Record<string, unknown> {
  const input = step.input ?? {};
  if (step.name === "keyword_search" && Array.isArray(input.terms)) {
    return { ...input, query: (input.terms as unknown[]).join(" ") };
  }
  if (DOC_TOOLS.has(step.name)) {
    const document = input.document ?? input.section ?? input.query;
    return document == null ? input : { ...input, document };
  }
  return input;
}

export function toToolCall(step: ApiStep): ToolCall {
  return {
    id: step.id,
    name: viewName(step),
    parentId: step.parent_id ?? undefined,
    label: step.label,
    status: step.status === "error" ? "error" : step.status === "done" ? "done" : "running",
    durationMs: step.duration_ms ?? 0,
    input: viewInput(step),
    output: (step.output as Record<string, unknown> | null | undefined) ?? null,
    summary: step.summary ?? "",
  };
}

export function toSource(s: ApiSource): Source {
  return {
    id: s.id,
    type: "doc",
    title: s.title,
    path: s.title,
    author: "",
    date: "",
    score: s.score ?? undefined,
    sections: s.sections.map((sec) => ({
      id: sec.id,
      heading: sec.heading,
      body: sec.body,
      blockType: sec.block_type,
      page: sec.page ?? undefined,
    })),
  };
}

export function toCitationMap(m: ApiCitationMap | undefined | null): CitationMap {
  const out: CitationMap = {};
  for (const [k, v] of Object.entries(m ?? {})) {
    const n = Number(k);
    if (Number.isInteger(n)) out[n] = { sourceId: v.source_id, sectionId: v.section_id };
  }
  return out;
}

/** ライブの 1 ターン（質問を送った直後）。 */
export function newTurn(query: string, ids: { runId?: string; messageId?: string } = {}): Turn {
  return {
    query,
    steps: [],
    answer: "",
    streaming: true,
    citationMap: {},
    sourceIds: [],
    sources: [],
    tokens: 0,
    durationMs: 0,
    status: "running",
    attachments: [],
    createdAt: new Date().toISOString(),
    messageId: ids.messageId,
    runId: ids.runId,
  };
}

function upsertStep(steps: ToolCall[], step: ToolCall): ToolCall[] {
  const i = steps.findIndex((s) => s.id === step.id);
  if (i < 0) return [...steps, step];
  const next = steps.slice();
  next[i] = step;
  return next;
}

function withSources(turn: Turn, sources: ApiSource[], citationMap: ApiCitationMap): Turn {
  const mapped = sources.map(toSource);
  return { ...turn, sources: mapped, sourceIds: mapped.map((s) => s.id), citationMap: toCitationMap(citationMap) };
}

/** イベントを 1 つ当てる（純関数。同じイベントを 2 回当てても壊れない）。 */
export function applyEvent(turn: Turn, ev: RunEvent): Turn {
  switch (ev.type) {
    case "run.started":
      return { ...turn, runId: ev.run_id, messageId: ev.message_id, modelId: ev.model_id };
    case "step":
      return { ...turn, steps: upsertStep(turn.steps, toToolCall(ev.step)) };
    case "answer.delta":
      return { ...turn, answer: turn.answer + ev.text };
    case "answer.reset":
      // 代替モデルへの切り替えなどで書き直す
      return { ...turn, answer: "" };
    case "sources":
      return withSources(turn, ev.sources, ev.citation_map);
    case "run.completed":
      return {
        ...withSources(turn, ev.sources, ev.citation_map),
        answer: ev.answer,
        streaming: false,
        status: "done",
        tokens: ev.tokens_in + ev.tokens_out,
        durationMs: ev.duration_ms,
        messageId: ev.message_id,
        noAnswerReason: ev.no_answer_reason ?? null,
        steps: turn.steps.map(settle),
      };
    case "run.failed":
      return { ...turn, streaming: false, status: "error", error: ev.message, steps: turn.steps.map(settle) };
    case "run.cancelled":
      return { ...turn, streaming: false, status: "cancelled", steps: turn.steps.map(settle) };
    default:
      return turn;
  }
}

/** 終わった run で「実行中」のまま残ったステップを閉じる。 */
function settle(s: ToolCall): ToolCall {
  return s.status === "running" ? { ...s, status: "error", summary: s.summary } : s;
}

export function isTerminal(ev: RunEvent): boolean {
  return ev.type === "run.completed" || ev.type === "run.failed" || ev.type === "run.cancelled";
}

/** 保存済みメッセージ（スレッド詳細）からターンを作る。 */
export function turnFromMessage(m: ApiMessage): Turn {
  const sources = (m.sources ?? []).map(toSource);
  return {
    query: m.query,
    steps: (m.steps ?? []).map(toToolCall),
    answer: m.answer,
    streaming: false,
    citationMap: toCitationMap(m.citation_map),
    sourceIds: sources.map((s) => s.id),
    sources,
    tokens: m.tokens_in + m.tokens_out,
    durationMs: m.duration_ms,
    status: m.status === "cancelled" ? "cancelled" : m.status === "failed" ? "error" : "done",
    attachments: [],
    createdAt: m.created_at,
    messageId: m.id,
    modelId: m.model_id ?? undefined,
    noAnswerReason: m.no_answer_reason ?? null,
    feedback: m.feedback
      ? {
          rating: m.feedback.rating,
          reasonTags: m.feedback.reason_tags as TurnFeedback["reasonTags"],
          comment: m.feedback.comment ?? null,
        }
      : null,
  };
}
