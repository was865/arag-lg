/** 回答の設定（specs/014-settings R3・R4）。範囲は API の AgentCfg.clamped と合わせる。 */

export interface AgentSettings {
  top_k: number;
  per_document: number;
  candidate_k: number;
  max_steps: number;
  max_retrieve_retries: number;
  parallel_tools: number;
  grade_threshold: number;
  require_citations: boolean;
  admit_unknown: boolean;
  followups: boolean;
  use_systems: boolean;
}

/** API（api/src/arag/agent/config.py）の既定値。 */
export const AGENT_DEFAULTS: AgentSettings = {
  top_k: 6,
  per_document: 3,
  candidate_k: 30,
  max_steps: 12,
  max_retrieve_retries: 1,
  parallel_tools: 3,
  grade_threshold: 0.3,
  require_citations: true,
  admit_unknown: true,
  followups: true,
  use_systems: true,
};

type NumKey = { [K in keyof AgentSettings]: AgentSettings[K] extends number ? K : never }[keyof AgentSettings];
type BoolKey = { [K in keyof AgentSettings]: AgentSettings[K] extends boolean ? K : never }[keyof AgentSettings];

/** term は技術者向けの一般的な用語（RAG・エージェントの文脈で通じる英語名）。画面ではラベルの横に小さく出す。 */
export type AgentField =
  | { kind: "number"; key: NumKey; label: string; term: string; hint: string; min: number; max: number; step: number; advanced?: boolean }
  | { kind: "bool"; key: BoolKey; label: string; term: string; hint: string; advanced?: boolean };

export const AGENT_FIELDS: AgentField[] = [
  { kind: "number", key: "top_k", term: "Top-K", label: "回答に使う資料の数", hint: "検索して回答に渡す箇所の数。増やすと網羅的になるが遅くなる。", min: 1, max: 20, step: 1 },
  { kind: "number", key: "per_document", term: "Per-document cap", label: "文書あたりの上限", hint: "同じ文書ばかりにならないようにする。0 は無制限。", min: 0, max: 20, step: 1 },
  { kind: "number", key: "max_steps", term: "Max agent steps", label: "最大ステップ数", hint: "検索や読み込みを繰り返せる回数の上限。", min: 5, max: 20, step: 1 },
  { kind: "number", key: "max_retrieve_retries", term: "Query rewrite retries", label: "再検索回数", hint: "関連する資料が足りないとき、言い換えて探し直す回数。", min: 0, max: 2, step: 1 },
  { kind: "bool", key: "require_citations", term: "Citation enforcement", label: "出典を必須にする", hint: "回答の各内容に出典番号を付けさせる。" },
  { kind: "bool", key: "admit_unknown", term: "Abstention", label: "回答できない場合は明示する", hint: "資料に無いことは推測せず「見つからない」と答える。" },
  { kind: "bool", key: "followups", term: "Follow-up suggestions", label: "続けて聞く質問を出す", hint: "回答の下に、次に聞けそうな質問を 2〜3 個出す。回答の後に作るので、回答は遅れない。" },
  { kind: "bool", key: "use_systems", term: "Enterprise systems (MCP)", label: "社内システムも調べる", hint: "管理者が登録した社内システム（在庫・保全・名簿など）から、今の値を読み取って答える。オフにすると社内の文書だけで答える。" },
  { kind: "number", key: "candidate_k", term: "Rerank candidates", label: "候補数", hint: "並べ替えの前に集める候補の数（回答に使う資料の数以上）。", min: 1, max: 50, step: 1, advanced: true },
  { kind: "number", key: "parallel_tools", term: "Parallel tool calls", label: "並列実行数", hint: "1 回の判断で並行して走らせる検索・読み込みの数。", min: 1, max: 8, step: 1, advanced: true },
  { kind: "number", key: "grade_threshold", term: "Relevance threshold", label: "関連とみなすしきい値", hint: "並べ替えの点数がこれ以上の資料を関連とみなす（0〜1）。", min: 0, max: 1, step: 0.05, advanced: true },
];

const num = (v: unknown, lo: number, hi: number, d: number, round = true) =>
  typeof v === "number" && Number.isFinite(v) ? Math.max(lo, Math.min(hi, round ? Math.round(v) : v)) : d;
const bool = (v: unknown, d: boolean) => (typeof v === "boolean" ? v : d);

export function clampAgentCfg(raw: unknown): AgentSettings {
  const o = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const d = AGENT_DEFAULTS;
  const top_k = num(o.top_k, 1, 20, d.top_k);
  return {
    top_k,
    per_document: num(o.per_document, 0, 20, d.per_document),
    candidate_k: Math.max(num(o.candidate_k, 1, 50, d.candidate_k), top_k),
    max_steps: num(o.max_steps, 5, 20, d.max_steps),
    max_retrieve_retries: num(o.max_retrieve_retries, 0, 2, d.max_retrieve_retries),
    parallel_tools: num(o.parallel_tools, 1, 8, d.parallel_tools),
    grade_threshold: Math.round(num(o.grade_threshold, 0, 1, d.grade_threshold, false) * 100) / 100,
    require_citations: bool(o.require_citations, d.require_citations),
    admit_unknown: bool(o.admit_unknown, d.admit_unknown),
    followups: bool(o.followups, d.followups),
    use_systems: bool(o.use_systems, d.use_systems),
  };
}

/** 送る値: 既定から変えた項目だけ。何も変えていなければ null（サーバの既定に従う）。 */
export function agentCfgPayload(cfg: AgentSettings): Partial<AgentSettings> | null {
  const out: Partial<AgentSettings> = {};
  for (const k of Object.keys(AGENT_DEFAULTS) as (keyof AgentSettings)[]) {
    if (cfg[k] !== AGENT_DEFAULTS[k]) (out as Record<string, unknown>)[k] = cfg[k];
  }
  return Object.keys(out).length ? out : null;
}

export const changedCount = (cfg: AgentSettings) => Object.keys(agentCfgPayload(cfg) ?? {}).length;
