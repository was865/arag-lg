import { describe, expect, it } from "vitest";
import { answerHtml, answerMarkdown, citedList, exportFileBase, linkCitations } from "@/lib/chat/export";
import type { Source, Turn } from "@/lib/types";

const sources: Source[] = [
  {
    id: "d1",
    type: "doc",
    title: "04-cross-page.pdf",
    path: "04-cross-page.pdf",
    author: "",
    date: "",
    sections: [
      { id: "s1", heading: "最終判断の補足", body: "MX-17はN9のため即時停止推奨に該当する。", page: 2 },
      { id: "s2", heading: "2. 点検表 A", body: "| 設備ID | 振動 |\n|---|---|\n| MX-17 | 0.91 |", page: 1 },
    ],
  },
];

const turn = {
  query: "MX-17 は運転を続けてよいですか？",
  answer: "例外的に認めています[1]。補足欄は「軸受け交換が必要」です[2]。[リンク](http://x)",
  citationMap: { 1: { sourceId: "d1", sectionId: "s1" }, 2: { sourceId: "d1", sectionId: "s2" } },
  sources,
  createdAt: "2026-11-09T06:33:00Z",
  modelId: "qwen3-8b",
} as unknown as Turn;

describe("export", () => {
  it("ファイル名に使えない文字を置き換え、長さを抑える", () => {
    expect(exportFileBase("A/B: C?")).toBe("A_B_ C_");
    expect(exportFileBase("   ")).toBe("answer");
    expect(exportFileBase("あ".repeat(60))).toHaveLength(40);
  });

  it("引用番号ごとの出典（文書・見出し・ページ）", () => {
    expect(citedList(turn)).toEqual([
      { n: 1, title: "04-cross-page.pdf", heading: "最終判断の補足", page: 2, body: "MX-17はN9のため即時停止推奨に該当する。" },
      { n: 2, title: "04-cross-page.pdf", heading: "2. 点検表 A", page: 1, body: "| 設備ID | 振動 |\n|---|---|\n| MX-17 | 0.91 |" },
    ]);
  });

  it("Markdown は質問・回答・出典の一覧をまとめる", () => {
    const md = answerMarkdown(turn);
    expect(md.startsWith("# MX-17 は運転を続けてよいですか？\n\n例外的に認めています[1]。")).toBe(true);
    expect(md).toContain("## 出典\n\n[1] 04-cross-page.pdf — 最終判断の補足（p.2）\n[2] 04-cross-page.pdf — 2. 点検表 A（p.1）");
  });

  it("引用記号はページ内の出典へのリンクにし、Markdown のリンクは触らない", () => {
    expect(linkCitations("A[1]B[2][9](http://x)", new Set([1, 2]))).toBe("A[1](#src-1)B[2](#src-2)[9](http://x)");
  });

  it("HTML は単独で開ける 1 枚のページで、文字列を必ずエスケープする", () => {
    // 本文の Markdown → HTML は呼び出し側（react-markdown）に任せる。ここでは目印を付けて返す
    const html = answerHtml({ ...turn, query: "<script>x</script>" } as Turn, (md) => `<div data-md>${md.length}</div>`);
    expect(html.startsWith("<!doctype html>")).toBe(true);
    expect(html).toContain("<title>&lt;script&gt;x&lt;/script&gt;</title>");
    expect(html).not.toContain("<script>x");
    expect(html).toContain(`<div data-md>${linkCitations(turn.answer, new Set([1, 2])).length}</div>`);
    expect(html).toContain('<li id="src-1">');
    expect(html).toContain("最終判断の補足");
    expect(html).toContain("prefers-color-scheme: dark");
  });
});

describe("renderMarkdown", () => {
  it("表・引用リンクを HTML にし、生の HTML はエスケープする", async () => {
    const { renderMarkdown } = await import("@/lib/chat/export-render");
    const html = renderMarkdown("A[1](#src-1) <b>x</b>\n\n| a | b |\n|---|---|\n| 1 | 2 |");
    expect(html).toContain('<a href="#src-1">1</a>');
    expect(html).toContain("&lt;b&gt;x&lt;/b&gt;");
    expect(html).toContain("<table>");
  });
});
