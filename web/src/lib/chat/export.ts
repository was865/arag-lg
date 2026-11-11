/** 回答の書き出し（Markdown・HTML ページ）。
 *
 * どちらも質問・回答・出典の一覧を 1 つにまとめ、[n] から出典をたどれるようにする。
 * Markdown → HTML の変換は画面と同じ react-markdown に任せる（export-render.tsx）。
 */
import type { Turn } from "@/lib/types";

export interface CitedItem {
  n: number;
  title: string;
  heading: string;
  /** 1 始まりのページ番号（docling のページ番号そのまま） */
  page?: number;
  body: string;
}

// [n] の引用記号（直後が "(" のものは Markdown のリンクなので除く）
const MARK_RE = /\[(\d+)\](?!\()/g;

export function exportFileBase(query: string): string {
  return (query || "").trim().slice(0, 40).replace(/[\\/:*?"<>|]/g, "_") || "answer";
}

/** 引用番号の順に、出典の文書・見出し・ページ・本文を並べる。 */
export function citedList(turn: Turn): CitedItem[] {
  const out: CitedItem[] = [];
  const nums = Object.keys(turn.citationMap ?? {})
    .map(Number)
    .sort((a, b) => a - b);
  for (const n of nums) {
    const ref = turn.citationMap[n];
    const src = turn.sources.find((s) => s.id === ref.sourceId);
    const sec = src?.sections.find((s) => s.id === ref.sectionId);
    if (!src || !sec) continue;
    out.push({ n, title: src.title, heading: sec.heading, page: sec.page ?? undefined, body: sec.body });
  }
  return out;
}

function where(c: CitedItem): string {
  const parts = [c.heading].filter(Boolean).join("");
  return `${c.title}${parts ? ` — ${parts}` : ""}${c.page != null ? `（p.${c.page}）` : ""}`;
}

export function answerMarkdown(turn: Turn): string {
  const cited = citedList(turn);
  const list = cited.length ? `\n\n---\n\n## 出典\n\n${cited.map((c) => `[${c.n}] ${where(c)}`).join("\n")}` : "";
  return `# ${turn.query.trim()}\n\n${turn.answer.trim()}${list}\n`;
}

/** [n] をページ内の出典へのリンク [n](#src-n) にする（出典の無い番号はそのまま）。 */
export function linkCitations(text: string, valid: Set<number>): string {
  return text.replace(MARK_RE, (m, d: string) => (valid.has(Number(d)) ? `[${d}](#src-${d})` : m));
}

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function stamp(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

const KATEX_CSS = "https://cdn.jsdelivr.net/npm/katex@0.17.0/dist/katex.min.css";

// 配色は画面と同じ「朱印」（globals.css の .theme-light / .theme-dark。specs/025 R47）
const STYLE = `
:root{--bg:#f5f4f1;--fg:#17181a;--fg2:#2b2d31;--muted:#6c7078;--line:rgba(23,24,26,.12);--soft:#eeede9;--accent:#b93321;--accent-soft:rgba(210,64,43,.10)}
@media (prefers-color-scheme: dark){:root{--bg:#111214;--fg:#ecebe7;--fg2:#d2d1cc;--muted:#9a9ca2;--line:rgba(255,255,255,.1);--soft:#1a1b1e;--accent:#f0806e;--accent-soft:rgba(238,100,80,.16)}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.8 -apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP","Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
main{max-width:720px;margin:0 auto;padding:56px 24px 72px}
.meta{font-size:12px;color:var(--muted);letter-spacing:.02em}
h1{font-size:24px;line-height:1.45;letter-spacing:-.01em;margin:10px 0 32px;font-weight:700}
.answer{color:var(--fg2)}
.answer p,.answer ul,.answer ol{margin:0 0 14px}
.answer h2,.answer h3{color:var(--fg);margin:28px 0 10px;line-height:1.4}
.answer h2{font-size:18px}.answer h3{font-size:16px}
.answer code{font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--soft);padding:1px 5px;border-radius:5px}
.answer pre{background:var(--soft);padding:14px 16px;border-radius:10px;overflow-x:auto}
.answer pre code{background:none;padding:0}
.answer blockquote{margin:0 0 14px;padding:2px 14px;border-left:2px solid var(--line);color:var(--muted)}
table{border-collapse:collapse;width:100%;margin:6px 0 16px;font-size:13px;line-height:1.55;display:block;overflow-x:auto}
th,td{border-bottom:.5px solid var(--line);padding:7px 12px;text-align:left;vertical-align:top;white-space:nowrap}
th{font-weight:600;color:var(--fg);border-bottom-color:var(--muted)}
a{color:var(--accent);text-decoration:none}
a[href^="#src-"]{display:inline-block;min-width:1.5em;margin:0 1px;padding:0 5px;border-radius:5px;background:var(--accent-soft);font-size:11px;font-weight:600;line-height:1.7;text-align:center;vertical-align:2px;font-variant-numeric:tabular-nums}
hr{border:0;border-top:.5px solid var(--line);margin:44px 0 24px}
h2.sources{font-size:13px;font-weight:600;color:var(--muted);letter-spacing:.04em;margin:0 0 14px}
ol.sources{list-style:none;margin:0;padding:0}
ol.sources>li{display:grid;grid-template-columns:2.2em 1fr;gap:0 6px;padding:14px 0;border-top:.5px solid var(--line)}
ol.sources>li:target{background:var(--accent-soft);border-radius:8px}
.n{font-size:12px;font-weight:600;color:var(--accent);font-variant-numeric:tabular-nums;padding-top:2px}
.doc{font-weight:600;font-size:14px}
.loc{font-size:12px;color:var(--muted)}
.excerpt{grid-column:2;margin-top:8px;font-size:13px;line-height:1.7;color:var(--fg2)}
.excerpt p{margin:0 0 8px}
.excerpt table{font-size:12px}
footer{margin-top:40px;font-size:11px;color:var(--muted)}
@media print{body{background:#fff;color:#000}main{padding:0}a[href^="#src-"]{background:none;color:#000}ol.sources>li{break-inside:avoid}}
`;

/** 単独で開ける 1 枚の HTML ページ。render は Markdown → HTML（生 HTML を通さない変換であること）。 */
export function answerHtml(turn: Turn, render: (md: string) => string): string {
  const cited = citedList(turn);
  const valid = new Set(cited.map((c) => c.n));
  const body = render(linkCitations(turn.answer.trim(), valid));
  const math = /\$/.test(turn.answer) ? `<link rel="stylesheet" href="${KATEX_CSS}">` : "";
  const meta = [stamp(turn.createdAt), turn.modelId ?? ""].filter(Boolean).map(esc).join(" · ");
  const items = cited
    .map((c) => {
      const loc = [c.heading, c.page != null ? `p.${c.page}` : ""].filter(Boolean).map(esc).join(" · ");
      return (
        `<li id="src-${c.n}"><span class="n">${c.n}</span><div><div class="doc">${esc(c.title)}</div>` +
        `${loc ? `<div class="loc">${loc}</div>` : ""}</div>` +
        `<div class="excerpt">${render(c.body)}</div></li>`
      );
    })
    .join("");
  const sources = cited.length ? `<hr><h2 class="sources">出典</h2><ol class="sources">${items}</ol>` : "";
  return (
    `<!doctype html><html lang="ja"><head><meta charset="utf-8">` +
    `<meta name="viewport" content="width=device-width, initial-scale=1">` +
    `<title>${esc(turn.query.trim())}</title>${math}<style>${STYLE}</style></head><body><main>` +
    `${meta ? `<div class="meta">${meta}</div>` : ""}<h1>${esc(turn.query.trim())}</h1>` +
    `<article class="answer">${body}</article>${sources}` +
    `<footer>ARag で書き出し</footer></main></body></html>`
  );
}
