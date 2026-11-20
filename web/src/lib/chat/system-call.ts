/**
 * 社内システム（MCP）の呼び出しを技術者が確かめるための形（specs/036）。
 * 段階の出力（api の mcp_tools が足す server・tool・args・rtt_ms・trace・result）から作る。
 */
import type { ToolCall } from "@/lib/types";

export interface SystemQuery {
  /** sql（SQLite。値を埋め込んだ文）・odoo（execute_kw の model.method(引数)） */
  lang: string;
  text: string;
  ms: number | null;
  rows: number | null;
}

export interface SystemCall {
  server: string;
  tool: string;
  args: Record<string, unknown>;
  /** ARag が測った往復 */
  rttMs: number | null;
  /** サーバの中（trace.ms） */
  serverMs: number | null;
  /** 問い合わせの時間の合計（分かるものだけ） */
  queryMs: number | null;
  calls: number | null;
  cached: boolean | null;
  backend: string | null;
  erpUser: string | null;
  traceId: string | null;
  queries: SystemQuery[];
  queriesDropped: number;
  /** モデルに渡した文 */
  modelText: string | null;
}

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === "string" && v ? v : null);
const obj = (v: unknown): Record<string, unknown> | null =>
  v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null;

export function callFromStep(step: ToolCall): SystemCall | null {
  const o = step.output ?? {};
  const [srv, tool] = (step.rawName ?? "").split("__");
  const server = str(o.server) ?? srv ?? null;
  const name = str(o.tool) ?? tool ?? null;
  if (!server || !name) return null;
  const tr = obj(o.trace) ?? {};
  const queries: SystemQuery[] = Array.isArray(tr.queries)
    ? (tr.queries as unknown[]).flatMap((q) => {
        const x = obj(q);
        return x && typeof x.text === "string"
          ? [{ lang: String(x.lang ?? "sql"), text: x.text, ms: num(x.ms), rows: num(x.rows) }]
          : [];
      })
    : [];
  const timed = queries.filter((q) => q.ms != null);
  return {
    server,
    tool: name,
    args: obj(o.args) ?? step.input,
    rttMs: num(o.rtt_ms),
    serverMs: num(tr.ms),
    queryMs: timed.length ? Math.round(timed.reduce((a, q) => a + (q.ms ?? 0), 0) * 10) / 10 : null,
    calls: num(tr.calls),
    cached: typeof tr.cached === "boolean" ? tr.cached : null,
    backend: str(tr.backend),
    erpUser: str(tr.erp_user),
    traceId: str(tr.id),
    queries,
    queriesDropped: num(tr.queries_dropped) ?? 0,
    modelText: str(o.result),
  };
}

/** `erp.list_suppliers(term="S-42")`。空の引数は除く。 */
export function callSignature(server: string, tool: string, args: Record<string, unknown>): string {
  const parts = Object.entries(args)
    .filter(([, v]) => v !== "" && v != null && !(Array.isArray(v) && v.length === 0))
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`);
  return `${server}.${tool}(${parts.join(", ")})`;
}

/** 往復をサーバの中と、それ以外（通信・MCP・整形）に分ける。往復が無ければ null。 */
export function timing({ rttMs, serverMs }: { rttMs: number | null; serverMs: number | null }) {
  if (rttMs == null) return null;
  const server = Math.min(serverMs ?? 0, rttMs);
  return { total: rttMs, server, rest: rttMs - server };
}

export function mcpRequest(c: SystemCall) {
  return { jsonrpc: "2.0", method: "tools/call", params: { name: c.tool, arguments: c.args } };
}

/** 応答の構造（structuredContent）。行・問い合わせは数だけにし、モデルへの文と画面用の項目は除く。 */
export function mcpResponse(output: Record<string, unknown>): Record<string, unknown> {
  const skip = new Set(["result", "server", "tool", "args", "rtt_ms", "n"]);
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(output)) {
    if (skip.has(k)) continue;
    if (k === "rows" && Array.isArray(v)) out.rows = `[${v.length} 行]`;
    else if (k === "trace" && obj(v)) {
      const tr = { ...(v as Record<string, unknown>) };
      if (Array.isArray(tr.queries)) tr.queries = `[${tr.queries.length} 件]`;
      out.trace = tr;
    } else out[k] = v;
  }
  return out;
}

export type CodeToken = { t: string; k: "kw" | "str" | "num" | "name" | "plain" };

const SQL_KW =
  /^(SELECT|FROM|WHERE|AND|OR|NOT|IN|IS|NULL|LIKE|JOIN|LEFT|INNER|OUTER|ON|AS|GROUP|BY|ORDER|HAVING|LIMIT|OFFSET|DISTINCT|COUNT|SUM|MAX|MIN|AVG|COALESCE|CASE|WHEN|THEN|ELSE|END|ASC|DESC|UNION|ALL|EXISTS|BETWEEN|WITH)$/i;

/** 等幅の文を控えめに色分けするための語の列（連結すると元の文に戻る）。 */
export function codeTokens(lang: string, text: string): CodeToken[] {
  const out: CodeToken[] = [];
  let rest = text;
  if (lang === "odoo") {
    const m = /^([a-z_][\w]*(?:\.[a-z_][\w]*)*)(\.[a-z_]\w*)(?=\()/i.exec(rest);
    if (m) {
      out.push({ t: m[1], k: "name" }, { t: m[2], k: "kw" });
      rest = rest.slice(m[0].length);
    }
  }
  const re = /('(?:[^'\\]|\\.|'')*'|"(?:[^"\\]|\\.)*")|(\b\d+(?:\.\d+)?\b)|([A-Za-z_]\w*)|(\s+|[^\sA-Za-z_\d'"]+|.)/gy;
  let m: RegExpExecArray | null;
  while ((m = re.exec(rest))) {
    if (m[1]) out.push({ t: m[1], k: "str" });
    else if (m[2]) out.push({ t: m[2], k: "num" });
    else if (m[3]) out.push({ t: m[3], k: lang === "sql" && SQL_KW.test(m[3]) ? "kw" : "plain" });
    else out.push({ t: m[0], k: "plain" });
  }
  // 隣り合う plain はまとめる（描画の要素を減らす）
  return out.reduce<CodeToken[]>((acc, tok) => {
    const last = acc[acc.length - 1];
    if (last && last.k === "plain" && tok.k === "plain") last.t += tok.t;
    else acc.push({ ...tok });
    return acc;
  }, []);
}
