/**
 * 時点の比較（specs/033 R20）: 回答の 1 文に、文書の出典が付いた数と社内システムの出典が付いた数が並んでいたら、
 * それを「文書（ある時点）／システム（今）」の小さな表にする。判定はコードで、見つからなければ何も出さない。
 *
 * 数と出典の対応: 出典の印 [n] の直前（前の印か文の頭から）にある最後の数を、その出典の値とする。
 * 単位（個・円・台・日・件・%・箱・袋）が違う組は比べない。括弧の中（「45個（11月20日取得）」の時点・部品番号）は値にしない。
 */
import { citationMarkerNumber, citationMarkerPattern } from "@/lib/citation-markers";
import type { CitationMap, Source } from "@/lib/types";

export interface CompareSide {
  value: string;
  n: number;
  title: string;
  /** システムの取得の時点（文書は無し） */
  at?: string;
}

export interface CompareRow {
  item: string;
  doc: CompareSide;
  system: CompareSide;
  same: boolean;
}

const NUM_RE = /(-?\d[\d,]*(?:\.\d+)?)\s*(個|円|台|日|件|%|％|箱|袋|kg|本|行)?/g;
const SENTENCE_RE = /[^。\n]+[。\n]?/g;
// 括弧の中は同じ長さの空白にする（位置を保つ）
const PAREN_RE = /（[^（）]*）|\([^()]*\)/g;
const maskParens = (s: string) => s.replace(PAREN_RE, (m) => " ".repeat(m.length));

interface Valued {
  n: number;
  num: number;
  text: string;
  unit: string;
  at: number;
}

function lastNumber(span: string): { num: number; text: string; unit: string; at: number } | null {
  let last: RegExpExecArray | null = null;
  for (const m of span.matchAll(NUM_RE)) last = m as RegExpExecArray;
  if (!last) return null;
  const raw = last[1];
  // 日付・番号の一部（2026-11-18・P-1042・PO-2026-0436・10/31・10 月）は値ではない
  let a = last.index;
  let b = last.index + raw.length;
  while (a > 0 && /[\w\-/.]/.test(span[a - 1])) a--;
  while (b < span.length && /[\w\-/.]/.test(span[b])) b++;
  const token = span.slice(a, b);
  if (/[A-Za-z]|\d-\d|\d\/\d/.test(token) || /^\s*(年|月)/.test(span.slice(last.index + raw.length))) return null;
  const unit = (last[2] ?? "").replace("％", "%");
  return { num: Number(raw.replace(/,/g, "")), text: `${raw}${unit ? (unit === "%" ? "" : " ") + unit : ""}`, unit, at: last.index };
}

function cleanItem(s: string): string {
  const segs = s
    .replace(citationMarkerPattern(), "")
    .replace(/[*_`#>]/g, "")
    .split(/[、,]/)
    .map((x) => x.trim())
    .filter(Boolean);
  // 主語の区切り（「…は」「…が」）があればそれ、無ければ最初の区切り
  const seg = segs.find((x) => /(は|が)$/u.test(x)) ?? segs[0] ?? "";
  return seg
    .replace(/[\s：:（(]+$/u, "")
    .replace(/(は|が|の|を|で|も)$/u, "")
    .trim()
    .slice(-28);
}

export function compareRows(answer: string, citationMap: CitationMap, sources: Source[]): CompareRow[] {
  const byId = new Map(sources.map((s) => [s.id, s]));
  const rows: CompareRow[] = [];
  const seen = new Set<string>();
  for (const sm of answer.matchAll(SENTENCE_RE)) {
    const sentence = sm[0];
    const valued: Valued[] = [];
    let from = 0;
    for (const m of sentence.matchAll(citationMarkerPattern())) {
      const n = Number(citationMarkerNumber(m as RegExpExecArray));
      const span = sentence.slice(from, m.index);
      from = (m.index ?? 0) + m[0].length;
      const got = lastNumber(maskParens(span.replace(citationMarkerPattern(), (x) => " ".repeat(x.length))));
      if (got && Number.isFinite(n)) valued.push({ n, ...got, at: (m.index ?? 0) - span.length + got.at });
    }
    const kind = (v: Valued) => {
      const ref = citationMap[v.n];
      const src = ref ? byId.get(ref.sourceId) : undefined;
      return src ? (src.type === "system" ? "system" : "doc") : null;
    };
    const doc = valued.find((v) => kind(v) === "doc");
    const sys = valued.find((v) => kind(v) === "system" && (!doc || v.unit === doc.unit));
    if (!doc || !sys) continue;
    const item = cleanItem(sentence.slice(0, Math.min(doc.at, sys.at)));
    if (!item || seen.has(item)) continue;
    seen.add(item);
    const side = (v: Valued): CompareSide => {
      const ref = citationMap[v.n];
      const src = byId.get(ref.sourceId)!;
      const sec = src.sections.find((s) => s.id === ref.sectionId);
      return { value: v.text, n: v.n, title: src.title, ...(sec?.record ? { at: sec.record.fetchedAt } : {}) };
    };
    rows.push({ item, doc: side(doc), system: side(sys), same: doc.num === sys.num });
  }
  return rows;
}
