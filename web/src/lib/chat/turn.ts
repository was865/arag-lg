/** run のイベント・保存済みメッセージを、旧版コンポーネントの view model（Turn）に写す（specs/005-agent D3）。
 *
 * サーバの型は OpenAPI から生成したもの。コンポーネントはグラフのノード名に依存せず、
 * ここで旧版の ToolName（retrieve・fetch_document・vector_search など）に合わせる。
 */
import type { components } from "@/lib/api/schema";
import type { TurnFeedback } from "@/lib/feedback-types";
import type { CitationMap, Source, ToolCall, ToolName, Turn, TurnImage } from "@/lib/types";

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
    // 旧版の API は意味検索の補完を「<親>:h」の子にしていた（親が見つからず消える）。保存済みの回答のため親へ付け替える
    parentId: step.parent_id?.replace(/:h$/, "") || undefined,
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

// ── 生成中の出典番号 ─────────────────────────────────────────────────
// サーバは回答の確定時に、番号を「回答に出た順」に振り直す（api/src/arag/agent/citations.py）。
// 生成中も同じ規則で見せて、完了の瞬間に番号が変わらないようにする。

const MARK_RE = /\[(\d+)\](?!\()/g;
const ATTR_RE = /\[\s*(?:資料\s*)?[nN]\s*[=＝]?\s*["']?([0-9０-９]+)["']?\s*\]/g;
// 角括弧なしで属性をそのまま書く形（「（資料 n="1"）」「資料 n="2" に記載」）。サーバの _BARE と同じ
const TAG = String.raw`(?:<\s*)?資料\s*[nN]\s*[=＝]\s*["'“”]?([0-9０-９]+)["'“”]?(?:\s*>)?`;
const BARE_RE = new RegExp(String.raw`[（(]\s*${TAG}\s*[）)]|${TAG}`, "g");
const FULLWIDTH_RE = /[【［]\s*([0-9０-９]+)\s*[】］]|\[\s*([０-９]+)\s*\]/g;
const GROUP_RE = /\[\s*(\d+(?:\s*[,，、]\s*\d+)+)\s*\](?!\()/g;
const REPEAT_RE = /\[(\d+)\](?:\[\1\](?!\())+/g;
// 末尾の書きかけの記号（"[1" や "[n="）。次の差分で閉じるまで出さない
const PARTIAL_RE = /[[【［][^\]】］\n]{0,12}$|[（(]?<?\s*資料\s*[nN]\s*[=＝]?\s*["'“”]?[0-9０-９]*$/;

const toNum = (s: string) => Number(s.normalize("NFKC"));

/** 生成中の回答の [n] を、出た順の 1, 2, 3… に振り直す。出典の無い番号は出さない。 */
export function liveCitations(raw: string, map: CitationMap): { answer: string; citationMap: CitationMap } {
  let text = raw.replace(PARTIAL_RE, "");
  text = text
    .replace(ATTR_RE, (_m, d: string) => `[${toNum(d)}]`)
    .replace(BARE_RE, (_m, a?: string, b?: string) => `[${toNum((a ?? b)!)}]`)
    .replace(FULLWIDTH_RE, (_m, a?: string, b?: string) => `[${toNum((a ?? b)!)}]`)
    .replace(GROUP_RE, (_m, inner: string) =>
      inner
        .split(/\s*[,，、]\s*/)
        .map((d) => `[${d}]`)
        .join(""),
    );
  const order: number[] = [];
  for (const m of text.matchAll(MARK_RE)) {
    const n = Number(m[1]);
    if (map[n] && !order.includes(n)) order.push(n);
  }
  const renum = new Map(order.map((old, i) => [old, i + 1]));
  text = text.replace(MARK_RE, (_m, d: string) => {
    const n = renum.get(Number(d));
    return n ? `[${n}]` : "";
  });
  text = text.replace(REPEAT_RE, "[$1]");
  const citationMap: CitationMap = {};
  for (const [old, n] of renum) citationMap[n] = map[old];
  return { answer: text, citationMap };
}

function relive(turn: Turn, raw: string, map: CitationMap): Turn {
  return { ...turn, rawAnswer: raw, rawCitationMap: map, ...liveCitations(raw, map) };
}

/** ライブの 1 ターン（質問を送った直後）。 */
export function newTurn(
  query: string,
  ids: { runId?: string; messageId?: string } = {},
  image?: TurnImage,
): Turn {
  return {
    query,
    image,
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
      return relive(turn, (turn.rawAnswer ?? turn.answer) + ev.text, turn.rawCitationMap ?? {});
    case "answer.reset":
      // 代替モデルへの切り替えなどで書き直す
      return relive(turn, "", turn.rawCitationMap ?? {});
    case "sources": {
      const next = withSources(turn, ev.sources, ev.citation_map);
      return relive(next, turn.rawAnswer ?? turn.answer, next.citationMap);
    }
    case "run.completed":
      return {
        ...withSources(turn, ev.sources, ev.citation_map),
        rawAnswer: undefined,
        rawCitationMap: undefined,
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

/** 保存済みメッセージの画像の URL（同一オリジンのプロキシ経由。cookie 認証で <img> から読める）。 */
export function messageImageUrl(threadId: string, messageId: string): string {
  return `/api/v1/threads/${threadId}/messages/${messageId}/image`;
}

/** 保存済みメッセージ（スレッド詳細）からターンを作る。 */
export function turnFromMessage(m: ApiMessage, threadId?: string): Turn {
  const sources = (m.sources ?? []).map(toSource);
  return {
    query: m.query,
    image:
      m.image && threadId
        ? { url: messageImageUrl(threadId, m.id), width: m.image.width, height: m.image.height, description: m.image.description ?? null }
        : undefined,
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
