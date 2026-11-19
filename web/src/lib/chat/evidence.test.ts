import { describe, expect, it } from "vitest";
import { evidenceList, groupHits, parseRetrieveHits, plainExcerpt, scoreScale, searchModeLabel, sectionLabel, searchStory, splitForFade } from "@/lib/chat/evidence";
import type { Source, ToolCall } from "@/lib/types";

const src = (id: string, title: string, sections: { id: string; heading: string; body: string; page?: number }[], score?: number): Source => ({
  id, type: "doc" as Source["type"], title, path: title, author: "", date: "", sections, score,
});

describe("evidenceList（回答の横に並べる根拠）", () => {
  const sources = [
    src("s1", "x02-保守記録.xlsx", [{ id: "a", heading: "9月", body: "PM-04 月次点検 30 分" }], 0.98),
    src("s2", "s01-点検票.pdf", [{ id: "b", heading: "所見", body: "軸受に摩耗あり", page: 1 }]),
  ];
  it("引用番号の順に、同じ箇所を指す番号は 1 枚にまとめる", () => {
    const out = evidenceList({ 1: { sourceId: "s1", sectionId: "a" }, 2: { sourceId: "s2", sectionId: "b" }, 3: { sourceId: "s1", sectionId: "a" } }, sources);
    expect(out.map((e) => e.numbers)).toEqual([[1, 3], [2]]);
    expect(out[0]).toMatchObject({ title: "x02-保守記録.xlsx", heading: "9月", excerpt: "PM-04 月次点検 30 分", score: 0.98 });
    expect(out[1].page).toBe(1);
  });
  it("出典が見つからない番号は出さない。長い本文は切り詰める", () => {
    const long = src("s3", "a.md", [{ id: "c", heading: "h", body: "あ".repeat(400) }]);
    const out = evidenceList({ 1: { sourceId: "none", sectionId: "x" }, 2: { sourceId: "s3", sectionId: "c" } }, [long]);
    expect(out).toHaveLength(1);
    expect(out[0].excerpt.length).toBeLessThanOrEqual(161);
    expect(out[0].excerpt.endsWith("…")).toBe(true);
  });
});

describe("plainExcerpt（抜粋から Markdown の記号を落とす）", () => {
  it("表は罫線の行を捨て、縦線を区切りの点にする", () => {
    expect(plainExcerpt("| 日付 | 設備ID |\n|---|:--|\n| 09-02 | PM-04 |")).toBe("日付 · 設備ID 09-02 · PM-04");
  });
  it("見出し・強調の記号を消し、空白を詰める", () => {
    expect(plainExcerpt("## 所見\n\n**軸受**に  摩耗あり")).toBe("所見 軸受に 摩耗あり");
  });
});

describe("parseRetrieveHits / searchStory（検索の過程）", () => {
  const result = "[1] x02-保守記録.xlsx — 9月\n本文 A\n\n[2] w01-規程.docx — 第 3 条\n本文 B\n\n[3] x02-保守記録.xlsx — 8月\n本文 C";
  const step = (over: Partial<ToolCall>): ToolCall => ({ id: "t", name: "retrieve", label: "", status: "done", durationMs: 10, input: {}, output: { result }, summary: "", ...over });
  it("出力の文字列を箇所ごとに分ける", () => {
    expect(parseRetrieveHits(result)).toHaveLength(3);
    expect(parseRetrieveHits(null)).toEqual([]);
  });
  it("探した文書（重複なし）と、そのうち引用したものを数える。引用したものを先に並べる", () => {
    const story = searchStory([step({}), step({ id: "u", name: "reasoning", output: null })], [src("s1", "x02-保守記録.xlsx", [])]);
    expect(story.searched).toBe(2);
    expect(story.cited).toBe(1);
    expect(story.files).toEqual([{ title: "x02-保守記録.xlsx", cited: true }, { title: "w01-規程.docx", cited: false }]);
  });
  it("聞き返しで終えたターン（specs/031）は clarify。引用が無くても注意にしない", () => {
    expect(searchStory([step({})], []).clarify).toBe(false);
    const sys = step({ id: "c", name: "system" as ToolCall["name"], input: { kind: "clarify", reason: "document_unspecified" }, output: null });
    expect(searchStory([step({}), sys], []).clarify).toBe(true);
    expect(searchStory([step({}), step({ id: "a", name: "ask_user" as ToolCall["name"], output: null })], []).clarify).toBe(true);
  });
  it("再ランキング前の候補（candidates）は探した文書に数えない", () => {
    const cands = step({ id: "c", name: "candidates", output: { hits: [{ title: "雑音.pdf", heading: "", score: 0.9 }] } });
    expect(searchStory([step({}), cands], []).searched).toBe(2);
  });
  it("この版の書式（<資料 n=… 文書=… 見出し=…>）も読む", () => {
    const text = '検索「HP-300」の結果 2 件（[n] が出典番号）:\n\n<資料 n="1" 文書="w03-手順書.docx" 見出し="手順書 > 2. 分解">\n本文 A\n</資料>\n\n<資料 n="2" 文書="w04-議事録.docx" 見出し="2. 対策">\n本文 B\n</資料>';
    const hits = parseRetrieveHits(text);
    expect(hits.map((h) => [h.n, h.title, h.heading])).toEqual([[1, "w03-手順書.docx", "手順書 > 2. 分解"], [2, "w04-議事録.docx", "2. 対策"]]);
    expect(hits[0].snippet).toBe("本文 A");
  });
  it("引用が 1 つも無くても、探して見つけた文書は数える（子の検索の hits からも集める）", () => {
    const child = step({ id: "c", name: "vector_search", output: { hits: [{ title: "a.docx", heading: "", score: 1 }, { title: "b.xlsx", heading: "", score: 0.5 }] } });
    const story = searchStory([step({ output: { result: "" } }), child], []);
    expect(story).toMatchObject({ searched: 2, cited: 0 });
    expect(story.files.every((f) => !f.cited)).toBe(true);
  });
  it("関連がほぼ 0 の文書は、探した数に入れない（引用していれば入れる）", () => {
    const result = '<資料 n="1" 文書="a.docx" 見出し="">本文</資料>\n\n<資料 n="2" 文書="noise.md" 見出し="">雑音</資料>\n\n<資料 n="3" 文書="c.md" 見出し="">雑音</資料>';
    const child = step({
      id: "c",
      name: "vector_search",
      output: { hits: [{ title: "a.docx", heading: "", score: 0.9 }, { title: "noise.md", heading: "", score: 0 }, { title: "c.md", heading: "", score: 0.004 }] },
    });
    const cited = [{ id: "s", type: "doc", title: "c.md", path: "c.md", author: "", date: "", sections: [] }] as Source[];
    const story = searchStory([step({ output: { result } }), child], cited);
    expect(story.files.map((f) => f.title).sort()).toEqual(["a.docx", "c.md"]);
    expect(story.searched).toBe(2);
  });
  it("検索していなければ 0 件", () => {
    expect(searchStory([], [])).toEqual({ searched: 0, cited: 0, files: [], clarify: false });
  });
});

describe("splitForFade（生成中の文字を小分けにする）", () => {
  it("空白で区切り、長い連なりは数文字ずつに分ける。つなげると元に戻る", () => {
    const text = "MX-17 の部品到着予定は翌営業日AMです。ただし停止コード N9 のため";
    const parts = splitForFade(text);
    expect(parts.join("")).toBe(text);
    expect(Math.max(...parts.map((p) => Array.from(p).length))).toBeLessThanOrEqual(8);
    expect(parts.length).toBeGreaterThan(4);
  });
  it("先に出た部分は、後ろに文字が足されても変わらない（出し直しにならない）", () => {
    const a = splitForFade("こんにちは、今日は");
    const b = splitForFade("こんにちは、今日はよい天気です");
    expect(b.slice(0, a.length - 1)).toEqual(a.slice(0, -1));
  });
});

describe("検索の明細（文書ごとのまとめ）", () => {
  const T3 = "w03-HP-300分解手順書_第3版.docx";
  const T2 = "w02-HP-300分解手順書_第2版.docx";
  const P3 = "HP-300 ポンプ分解・組立手順書（第3版）";
  const hits = [
    { title: T3, heading: `${P3} > 2. 分解`, score: 1.0 },
    { title: T2, heading: "HP-300 ポンプ分解・組立手順書（第2版） > 2. 分解", score: 0.999 },
    { title: T3, heading: `${P3} > 1. 準備`, score: 0.99 },
    { title: T3, heading: P3, score: 0.95 },
  ];
  it("見出しの道筋から箇所の名前だけを取り出す。道筋が題だけなら空（文書の冒頭）", () => {
    expect(sectionLabel(`${P3} > 2. 分解`)).toBe("2. 分解");
    expect(sectionLabel(`${P3} > 2. 分解 > 2.1 外す`)).toBe("2. 分解 › 2.1 外す");
    expect(sectionLabel(P3)).toBe("");
    expect(sectionLabel("")).toBe("");
  });
  it("文書ごとにまとめ、いちばん高いスコアの順に並べる。引用した文書に印を付ける", () => {
    const groups = groupHits(hits, new Set([T3]));
    expect(groups.map((g) => g.title)).toEqual([T3, T2]);
    expect(groups[0]).toMatchObject({ best: 1.0, cited: true });
    expect(groups[0].sections.map((s) => s.label)).toEqual(["2. 分解", "1. 準備", ""]);
    expect(groups[1].cited).toBe(false);
  });
  it("方式の表示名と、棒の最大値", () => {
    expect(searchModeLabel("hybrid", "vector_search")).toBe("ハイブリッド検索");
    expect(searchModeLabel(undefined, "bm25_search")).toBe("キーワード検索");
    expect(searchModeLabel(undefined, "vector_search")).toBe("意味での検索");
    expect(scoreScale(hits)).toBe(1);
    expect(scoreScale([{ score: 12.5 }, { score: 3 }])).toBe(12.5);
  });
});
