/** 文書ビューアの純粋関数（specs/007-document-viewer）。 */

/** 章本文の `![alt](assets/x.png)` を文書のアセット API に向ける（R6）。 */
export function resolveAssets(text: string, docId: string): string {
  const base = `/api/v1/documents/${encodeURIComponent(docId)}/assets/`;
  return text.replace(/(!\[[^\]]*\]\()assets\/([A-Za-z0-9._-]+)\)/g, (_, head: string, name: string) => `${head}${base}${name})`);
}

/** 目次の字下げ: 最も浅い見出しを 0 とし、深すぎるものは 4 で止める（R5）。 */
export function outlineIndent(sections: { level: number }[]): number[] {
  if (!sections.length) return [];
  const min = Math.min(...sections.map((s) => s.level));
  return sections.map((s) => Math.min(4, s.level - min));
}

/** スクロール位置で読んでいる章（上端から 80px の余白を見込む）。 */
export function activeSectionId(tops: { id: string; top: number }[], scrollTop: number): string | null {
  let cur: string | null = tops[0]?.id ?? null;
  for (const t of tops) {
    if (t.top - 80 <= scrollTop) cur = t.id;
    else break;
  }
  return cur;
}

const SEP_RE = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const cells = (line: string) => {
  const t = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return t.split("|").map((c) => esc(c.trim()));
};

/** Markdown の | 表（2 行目が区切り行のもの）を HTML 表にする。整形表示で表として描くため（R3）。 */
export function pipeTablesToHtml(text: string): string {
  const lines = text.split("\n");
  const out: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const head = lines[i]!;
    if (head.trim().startsWith("|") && i + 1 < lines.length && SEP_RE.test(lines[i + 1]!)) {
      const rows: string[] = [];
      let j = i + 2;
      while (j < lines.length && lines[j]!.trim().startsWith("|")) rows.push(lines[j++]!);
      const th = cells(head).map((c) => `<th>${c}</th>`).join("");
      const tb = rows.map((r) => `<tr>${cells(r).map((c) => `<td>${c}</td>`).join("")}</tr>`).join("");
      out.push(`<table><thead><tr>${th}</tr></thead><tbody>${tb}</tbody></table>`);
      i = j - 1;
    } else out.push(head);
  }
  return out.join("\n");
}
