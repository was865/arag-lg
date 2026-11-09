/** セクション本文を順序付きセグメントへ分割する。
 *  本文は素のテキスト・HTML 表・Markdown 表（docling の出力）・markdown 画像・mermaid 図の混在を取りうる。
 *  画像の src は tools.ts で絶対 API パスへ解決済み。 */
export type BodySegment =
  | { kind: "text"; text: string }
  | { kind: "table"; html: string }
  | { kind: "image"; src: string; alt: string }
  | { kind: "mermaid"; code: string };

// 順に: ```mermaid フェンス（閉じ ``` は後続テキストに密着しうるので非貪欲）、
// <table>…</table> ブロック、markdown 画像 ![alt](src)。
// グループ: [1]=mermaid コード, [2]=画像 alt, [3]=画像 src。
const SEG_RE =
  /```mermaid[ \t]*\r?\n([\s\S]*?)```|<table[\s\S]*?<\/table>|!\[([^\]]*)\]\(([^)\s]+)\)/gi;

const ROW_RE = /^\s*\|/;
// 区切り行: |---|:-:|---:|（両端の | は省略可）
const SEP_RE = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/;

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** 表の 1 行をセルに分ける。\| はセル内の | として扱う。末尾の | が無い行（途中で切れた行）も受ける。 */
function splitRow(line: string): string[] {
  const inner = line.trim().replace(/^\|/, "").replace(/(?<!\\)\|$/, "");
  return inner.split(/(?<!\\)\|/).map((c) => c.replace(/\\\|/g, "|").trim());
}

/** Markdown の表を、既存の表描画（HtmlTable）が読める HTML にする。 */
export function markdownTableToHtml(lines: string[]): string {
  const [head, , ...rows] = lines.map(splitRow);
  const cells = (cs: string[], tag: "th" | "td") => cs.map((c) => `<${tag}>${escapeHtml(c)}</${tag}>`).join("");
  const body = rows.map((cs) => `<tr>${cells(cs, "td")}</tr>`).join("");
  return `<table><thead><tr>${cells(head, "th")}</tr></thead><tbody>${body}</tbody></table>`;
}

export function parseSectionBody(body: string): BodySegment[] {
  const segs: BodySegment[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  const pushPlain = (raw: string) => {
    const text = raw.trim();
    if (text) segs.push({ kind: "text", text });
  };
  // 本文中の Markdown 表（見出し行 + 区切り行 + | で始まる行の並び）を表として切り出す
  const pushText = (raw: string) => {
    const lines = raw.split(/\r?\n/);
    let start = 0;
    let i = 0;
    while (i < lines.length) {
      if (ROW_RE.test(lines[i]) && i + 1 < lines.length && SEP_RE.test(lines[i + 1]) && lines[i + 1].includes("-")) {
        let end = i + 2;
        while (end < lines.length && ROW_RE.test(lines[end])) end++;
        pushPlain(lines.slice(start, i).join("\n"));
        segs.push({ kind: "table", html: markdownTableToHtml(lines.slice(i, end)) });
        start = i = end;
      } else {
        i++;
      }
    }
    pushPlain(lines.slice(start).join("\n"));
  };
  SEG_RE.lastIndex = 0;
  while ((m = SEG_RE.exec(body)) !== null) {
    pushText(body.slice(last, m.index));
    if (m[1] !== undefined) {
      segs.push({ kind: "mermaid", code: m[1].trim() });
    } else if (m[0][0] === "<") {
      segs.push({ kind: "table", html: m[0] });
    } else {
      segs.push({ kind: "image", alt: m[2] ?? "", src: m[3] ?? "" });
    }
    last = m.index + m[0].length;
  }
  pushText(body.slice(last));
  return segs;
}
