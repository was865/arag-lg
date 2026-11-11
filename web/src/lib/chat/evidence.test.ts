import { describe, expect, it } from "vitest";
import { evidenceList, parseRetrieveHits, plainExcerpt, searchStory, splitForFade } from "@/lib/chat/evidence";
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
  it("検索していなければ 0 件", () => {
    expect(searchStory([], [])).toEqual({ searched: 0, cited: 0, files: [] });
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
