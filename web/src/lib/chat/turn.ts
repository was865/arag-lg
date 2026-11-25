/** run のイベント・保存済みメッセージを、旧版コンポーネントの view model（Turn）に写す（specs/005-agent D3）。
 *
 * サーバの型は OpenAPI から生成したもの。コンポーネントはグラフのノード名に依存せず、
 * ここで旧版の ToolName（retrieve・fetch_document・vector_search など）に合わせる。
 */
import type { components } from "@/lib/api/schema";
import type { TurnFeedback } from "@/lib/feedback-types";
import type { CitationMap, Source, SystemRecord, ToolCall, ToolName, Turn, TurnImage } from "@/lib/types";

type S = components["schemas"];
export type RunEvent = S["RunEvent"];
export type ApiStep = S["Step"];
export type ApiSource = S["SourceView"];
export type ApiMessage = S["MessageOut"];
export type ApiCitationMap = Record<string, S["CitationRef"]>;

const DOC_TOOLS = new Set(["list_documents", "get_outline", "read_section", "read_document"]);

/** サーバのステップ名を旧版の表示種別に写す。 */
function viewName(step: ApiStep): ToolName {
  // 社内システム（MCP）のツールは「<サーバ名>__<ツール名>」（specs/032）
  if (step.name.includes("__")) return "system_query";
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
    ...(step.name.includes("__") ? { rawName: step.name } : {}),
    // 旧版の API は意味検索の補完を「<親>:h」の子にしていた（親が見つからず消える）。保存済みの回答のため親へ付け替える
    parentId: step.parent_id?.replace(/:h$/, "") || undefined,
    label: step.label,
    status: step.status === "error" ? "error" : step.status === "done" ? "done" : "running",
    durationMs: step.duration_ms ?? 0,
    input: viewInput(step),
    output: (step.output as Record<string, unknown> | null | undefined) ?? null,
    summary: step.summary ?? "",
    // 出した節点（specs/029。古い記録には無い。流れの表示が推定する）
    ...(step.node ? { node: step.node } : {}),
  };
}

export function toSource(s: ApiSource): Source {
  return {
    id: s.id,
    type: s.kind === "system" ? "system" : "doc",
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
      ...(sec.record ? { record: toRecord(sec.record) } : {}),
    })),
  };
}

function toRecord(r: S["RecordView"]): SystemRecord {
  return {
    system: r.system,
    server: r.server,
    tool: r.tool,
    title: r.title,
    args: r.args,
    fetchedAt: r.fetched_at,
    basis: r.basis,
    columns: r.columns,
    rows: r.rows,
    total: r.total,
    restricted: r.restricted,
    note: r.note ?? null,
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
// サーバは回答の確定時に、番号を「回答に出た順」に振り直す（api/src/arag/agent/domain/citations.py）。
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
  if (i < 0) return explainFallback([...steps, step]);
  const next = steps.slice();
  next[i] = step;
  return explainFallback(next);
}

const OLD_KEYWORD_ZERO = /^0 件（最高スコア/;
const OLD_TOOL_TOTAL = /^資料 (\d+) 件$/;

/**
 * キーワード検索（完全一致）が 0 件で意味検索に切り替えた流れを、各ステップで分かるようにする。
 * 新しい API は要約を書いて返すが、保存済みの回答（旧版）は要約が素っ気ないのでここで補う。純関数・何度当てても同じ。
 */
export function explainFallback(steps: ToolCall[]): ToolCall[] {
  let out = steps;
  const patch = (i: number, p: Partial<ToolCall>) => {
    if (out === steps) out = steps.slice();
    out[i] = { ...out[i]!, ...p };
  };
  steps.forEach((s, i) => {
    if (s.name !== "bm25_search" || s.status !== "done" || !s.parentId) return;
    const hits = s.output?.hits;
    if (!Array.isArray(hits) || hits.length > 0) return;
    const j = steps.findIndex((x, k) => k > i && x.parentId === s.parentId && x.name === "vector_search");
    if (j < 0) return;
    if (!s.output?.fallback || OLD_KEYWORD_ZERO.test(s.summary)) {
      patch(i, {
        output: { ...s.output, fallback: true },
        summary: OLD_KEYWORD_ZERO.test(s.summary) ? "0 件（すべての語を含む箇所なし）" : s.summary,
      });
    }
    if (steps[j]!.label === "検索") patch(j, { label: "セマンティック検索で補完" });
    const p = steps.findIndex((x) => x.id === s.parentId);
    const m = p >= 0 ? OLD_TOOL_TOTAL.exec(steps[p]!.summary) : null;
    if (m) patch(p, { summary: `完全一致 0 件 → セマンティック検索で資料 ${m[1]} 件` });
  });
  return out;
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
      return relive(
        { ...turn, staleAnswer: undefined },
        (turn.rawAnswer ?? turn.answer) + ev.text,
        turn.rawCitationMap ?? {},
      );
    case "answer.reset":
      // 確認での差し戻し・代替モデルへの切り替えなどで書き直す。それまでの下書きは、次の本文が届くまで残す
      return relive(
        { ...turn, staleAnswer: turn.answer.trim() ? turn.answer : turn.staleAnswer },
        "",
        turn.rawCitationMap ?? {},
      );
    case "sources": {
      const next = withSources(turn, ev.sources, ev.citation_map);
      return relive(next, turn.rawAnswer ?? turn.answer, next.citationMap);
    }
    case "run.completed":
      return {
        ...withSources(turn, ev.sources, ev.citation_map),
        rawAnswer: undefined,
        rawCitationMap: undefined,
        staleAnswer: undefined,
        answer: ev.answer,
        streaming: false,
        status: "done",
        tokens: ev.tokens_in + ev.tokens_out,
        durationMs: ev.duration_ms,
        messageId: ev.message_id,
        noAnswerReason: ev.no_answer_reason ?? null,
        suggestions: ev.suggestions ?? [],
        followupsPending: Boolean(ev.followups_pending),
        steps: turn.steps.map(settle),
      };
    case "followups":
      // 完了の後に届く続けて聞く候補（specs/028 T24）。次の質問を送った後に届いても、最後のターンでなければ出ない
      return { ...turn, suggestions: ev.suggestions ?? [], followupsPending: false };
    case "run.failed":
      return {
        ...turn,
        // 心拍が途絶えた run（runner_lost）はメッセージを保存していない（報告・分岐の元にできない）
        messageId: ev.code === "runner_lost" ? undefined : turn.messageId,
        staleAnswer: undefined,
        streaming: false,
        status: "error",
        error: ev.message,
        steps: turn.steps.map(settle),
      };
    case "run.cancelled":
      return { ...turn, staleAnswer: undefined, streaming: false, status: "cancelled", steps: turn.steps.map(settle) };
    default:
      return turn;
  }
}

/** 終わった run で「実行中」のまま残ったステップを閉じる。 */
function settle(s: ToolCall): ToolCall {
  return s.status === "running" ? { ...s, status: "error", summary: s.summary } : s;
}

/** ストリームを閉じるイベントか。候補を後から送る完了（followups_pending）は閉じず、followups で閉じる。 */
export function isTerminal(ev: RunEvent): boolean {
  if (ev.type === "run.completed") return !ev.followups_pending;
  return ev.type === "followups" || ev.type === "run.failed" || ev.type === "run.cancelled";
}

/** run が終わったイベントか（回答の確定。続けて聞く候補を待たない）。 */
export function endsRun(ev: RunEvent): boolean {
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
    steps: explainFallback((m.steps ?? []).map(toToolCall)),
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
    suggestions: m.suggestions ?? [],
    feedback: m.feedback
      ? {
          rating: m.feedback.rating,
          reasonTags: m.feedback.reason_tags as TurnFeedback["reasonTags"],
          comment: m.feedback.comment ?? null,
        }
      : null,
  };
}
