/** 首ページ・サイドバー・コマンドパレットの表示用の計算（specs/025 R44）。 */

/** ナレッジベースの字標（角丸の四角に 1 字）に出す字。色は付けない（並んだときに騒がしくなるため。specs/025 R44 見直し）。 */
export function kbGlyph(label: string): string {
  // 「評価: jqara」のような「種別: 名前」は、並んだときに見分けが付くよう名前の側の字を使う
  const name = (label.split(/[:：]/).pop() ?? label).trim() || label.trim();
  return (Array.from(name)[0] ?? "・").toUpperCase();
}

export interface Suggestion {
  id: string;
  filename: string;
  /** 入力欄に入れる文面（雛形。LLM では作らない） */
  text: string;
}

interface DocLike {
  id: string;
  filename: string;
}

const TABULAR = new Set(["xlsx", "xls", "csv"]);

/** よく引用される文書（足りなければ最近の文書）から、質問の候補を 3 件まで作る。 */
export function suggestionsFrom(
  overview: { top_cited: { document: DocLike }[]; recent: DocLike[] } | null | undefined,
  max = 3,
): Suggestion[] {
  if (!overview) return [];
  const seen = new Set<string>();
  const out: Suggestion[] = [];
  for (const doc of [...overview.top_cited.map((c) => c.document), ...overview.recent]) {
    if (seen.has(doc.id) || out.length >= max) continue;
    seen.add(doc.id);
    const dot = doc.filename.lastIndexOf(".");
    const base = dot > 0 ? doc.filename.slice(0, dot) : doc.filename;
    const ext = dot > 0 ? doc.filename.slice(dot + 1).toLowerCase() : "";
    const text = TABULAR.has(ext) ? `「${base}」の内容を要約してください` : `「${base}」の要点を教えてください`;
    out.push({ id: doc.id, filename: doc.filename, text });
  }
  return out;
}

const fold = (s: string) => s.normalize("NFKC").toLowerCase().replace(/[‐‑‒–—−ー－]/g, "-");

/** 絞り込み: 空白で区切った語をすべて含めば合う（大文字小文字・全角半角は区別しない）。 */
export function matchesQuery(label: string, query: string): boolean {
  const hay = fold(label);
  return fold(query).split(/\s+/).filter(Boolean).every((w) => hay.includes(w));
}
