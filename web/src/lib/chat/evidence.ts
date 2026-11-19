/** 会話画面の「根拠」まわりの表示用の計算（specs/025 R45・R20）。 */
import type { CitationMap, Source, ToolCall } from "@/lib/types";

export interface Evidence {
  /** この箇所を指す引用番号（小さい順） */
  numbers: number[];
  sourceId: string;
  sectionId: string;
  title: string;
  heading: string;
  page?: number;
  /** 抜粋（長ければ切り詰める） */
  excerpt: string;
  /** 関連度（0〜1）。取れていなければ undefined */
  score?: number;
  /** 社内システムの結果（specs/032） */
  system?: boolean;
}

const EXCERPT_MAX = 160;

/** 引用番号 → 出典の対応から、回答の横に並べる根拠を作る。同じ箇所を指す番号は 1 枚にまとめる。 */
export function evidenceList(citationMap: CitationMap, sources: Source[]): Evidence[] {
  const byKey = new Map<string, Evidence>();
  for (const n of Object.keys(citationMap).map(Number).sort((a, b) => a - b)) {
    const { sourceId, sectionId } = citationMap[n];
    const key = `${sourceId}|${sectionId}`;
    const hit = byKey.get(key);
    if (hit) {
      hit.numbers.push(n);
      continue;
    }
    const source = sources.find((s) => s.id === sourceId);
    if (!source) continue;
    const section = source.sections.find((s) => s.id === sectionId) ?? source.sections[0];
    const body = plainExcerpt(section?.body ?? "");
    byKey.set(key, {
      numbers: [n],
      sourceId,
      sectionId,
      title: source.title,
      heading: section?.heading ?? "",
      page: section?.page,
      excerpt: body.length > EXCERPT_MAX ? `${body.slice(0, EXCERPT_MAX)}…` : body,
      score: source.score,
      ...(source.type === "system" ? { system: true } : {}),
    });
  }
  return [...byKey.values()];
}

/** 抜粋用に Markdown の記号を落とす（表の罫線の行を捨て、縦線は区切りの点に、見出し・強調の記号は消す）。 */
export function plainExcerpt(body: string): string {
  return body
    .split("\n")
    .filter((line) => !/^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(line))
    .map((line) => line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").replace(/\s*\|\s*/g, " · "))
    .join(" ")
    .replace(/[#*`>]+/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export interface RetrieveHit {
  n: number;
  title: string;
  heading: string;
  snippet: string;
}

/**
 * 検索ツールの出力テキストを箇所ごとに分ける。2 つの書式を読む:
 * - この版: `<資料 n="1" 文書="題" 見出し="道筋">本文</資料>`
 * - 旧版: `[1] 題 — 見出し` + 改行 + 本文（空行区切り）
 */
export function parseRetrieveHits(text: unknown): RetrieveHit[] {
  if (typeof text !== "string" || !text) return [];
  const hits: RetrieveHit[] = [];
  // 属性の値（見出しの道筋）に ">" が入るので、引用符の中は読み飛ばす
  const tag = /<資料\s+((?:[^>"]|"[^"]*")*)>([\s\S]*?)<\/資料>/g;
  let m: RegExpExecArray | null;
  while ((m = tag.exec(text)) !== null) {
    const attr = (name: string) => m![1].match(new RegExp(`${name}="([^"]*)"`))?.[1] ?? "";
    const n = Number(attr("n"));
    if (Number.isFinite(n) && attr("文書")) hits.push({ n, title: attr("文書"), heading: attr("見出し"), snippet: m[2].trim() });
  }
  if (hits.length) return hits;
  // 各エントリは空行 + `[N]` 行始まりで区切る。最初のエントリは split で先頭に来る。
  for (const part of text.split(/\n\n(?=\[\d+\])/)) {
    const old = part.match(/^\[(\d+)\]\s*(.+?)\s*—\s*([^\n]+)\n?([\s\S]*)$/);
    if (old) hits.push({ n: Number(old[1]), title: old[2].trim(), heading: old[3].trim(), snippet: old[4].trim() });
  }
  return hits;
}

export interface SearchStory {
  /** 探して見つけた文書の数（重複なし） */
  searched: number;
  /** そのうち回答に引用した文書の数 */
  cited: number;
  /** 見つけた文書名（引用したものを先に） */
  files: { title: string; cited: boolean }[];
  /** 聞き返しで終えたターンか（モデルの ask_user か、システムの聞き返し。specs/031）。引用が無いのは当然 */
  clarify: boolean;
}

/** これより低い関連度は「関連なし」とみなす（検索が件数を満たすために返した雑音）。 */
export const NEGLIGIBLE_SCORE = 0.01;

/** エージェントの段階から「何件探し、何件引用したか」を作る。関連がほぼ 0 の文書は（引用していなければ）数えない。 */
export function searchStory(steps: ToolCall[], sources: Source[]): SearchStory {
  const citedTitles = new Set(sources.map((s) => s.title));
  const titles: string[] = [];
  const add = (title: unknown) => {
    if (typeof title === "string" && title && !titles.includes(title)) titles.push(title);
  };
  // 子の検索の hits で、どの箇所も関連がほぼ 0 だった文書（件数を埋めるだけの雑音）
  const best = new Map<string, number>();
  for (const step of steps) {
    // 再ランキング前の候補（候補の取得）は、まだ絞る前の一覧なので「見つけた文書」には数えない
    if (step.name === "candidates") continue;
    // 親の段階は出力の文字列から、子の検索の段階は hits の一覧から、見つけた文書の題を集める
    for (const hit of parseRetrieveHits(step.output?.result)) add(hit.title);
    const hits = step.output?.hits;
    if (!Array.isArray(hits)) continue;
    for (const h of hits as { title?: unknown; score?: unknown }[]) {
      add(h.title);
      if (typeof h.title === "string" && typeof h.score === "number") best.set(h.title, Math.max(best.get(h.title) ?? -Infinity, h.score));
    }
  }
  const weak = (t: string) => !citedTitles.has(t) && (best.get(t) ?? Infinity) < NEGLIGIBLE_SCORE;
  titles.splice(0, titles.length, ...titles.filter((t) => !weak(t)));
  // 引用したのに検索結果の文字列に現れない文書（題名の表記ゆれなど）も数に入れる
  for (const t of citedTitles) if (!titles.includes(t)) titles.push(t);
  const files = titles.map((title) => ({ title, cited: citedTitles.has(title) }));
  files.sort((a, b) => Number(b.cited) - Number(a.cited));
  const clarify = steps.some((s) => s.name === "ask_user" || (s.name === "system" && s.input?.kind === "clarify"));
  return { searched: titles.length, cited: sources.length, files, clarify };
}

const FADE_CHUNK = 8;

/**
 * 生成中の文字を小分けにする（1 つずつ淡く出すため）。空白で区切り、長い連なり（日本語など）は数文字ずつに分ける。
 * 前から順に切るので、後ろに文字が足されても先に出た部分は変わらない。
 */
export function splitForFade(text: string): string[] {
  const out: string[] = [];
  for (const piece of text.split(/(\s+)/)) {
    if (!piece) continue;
    const chars = Array.from(piece);
    for (let i = 0; i < chars.length; i += FADE_CHUNK) out.push(chars.slice(i, i + FADE_CHUNK).join(""));
  }
  return out;
}

// ── 検索の明細（「詳細」の中。specs/025 見直し） ─────────────────────────────

/** 検索の方式の表示名。mode が無ければツール名から決める。 */
export function searchModeLabel(mode: unknown, toolName: string): string {
  const m = typeof mode === "string" ? mode.toLowerCase() : "";
  if (m === "hybrid") return "ハイブリッド検索";
  if (m === "dense" || m === "vector" || m === "semantic") return "意味での検索";
  if (m === "sparse" || m === "bm25" || m === "keyword") return "キーワード検索";
  return toolName === "bm25_search" ? "キーワード検索" : "意味での検索";
}

/**
 * 見出しの道筋（"文書の題 > 2. 分解"）から、その箇所の名前だけを取り出す。
 * 文書の題はグループの見出しに出すので、行では繰り返さない。道筋が無ければ空（文書の冒頭）。
 */
export function sectionLabel(heading: string): string {
  const parts = heading.split(">").map((p) => p.trim()).filter(Boolean);
  // 1 段だけ（文書の題そのもの）なら、箇所の名前は無い
  return parts.length <= 1 ? "" : parts.slice(1).join(" › ");
}

export interface HitGroup {
  title: string;
  /** この文書の中でいちばん高いスコア */
  best: number;
  /** 回答に引用された文書か */
  cited: boolean;
  sections: { label: string; score: number }[];
}

/** 検索で見つけた箇所を文書ごとにまとめる。文書はいちばん高いスコアの順、箇所もスコアの順。 */
export function groupHits(hits: { title: string; heading: string; score: number }[], citedTitles: ReadonlySet<string> = new Set()): HitGroup[] {
  const groups = new Map<string, HitGroup>();
  for (const h of hits) {
    const g = groups.get(h.title) ?? { title: h.title, best: -Infinity, cited: citedTitles.has(h.title), sections: [] };
    g.best = Math.max(g.best, h.score);
    g.sections.push({ label: sectionLabel(h.heading ?? ""), score: h.score });
    groups.set(h.title, g);
  }
  const out = [...groups.values()];
  for (const g of out) g.sections.sort((a, b) => b.score - a.score);
  return out.sort((a, b) => b.best - a.best);
}

/** スコアの棒の最大値。0〜1 の類似度はそのまま（1 が満杯）、BM25 のように 1 を超えるものは一覧の最大値で割る。 */
export function scoreScale(hits: { score: number }[]): number {
  const max = Math.max(0, ...hits.map((h) => h.score));
  return max > 1 ? max : 1;
}
