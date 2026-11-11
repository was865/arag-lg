import { describe, expect, it } from "vitest";
import { GLYPH_COLORS, kbGlyph, matchesQuery, suggestionsFrom } from "@/lib/home";

describe("kbGlyph（ナレッジベースの字標）", () => {
  it("名前の先頭の字を出す。「種別: 名前」の形なら名前の側の字を使う", () => {
    expect(kbGlyph("a", "保守・点検").char).toBe("保");
    expect(kbGlyph("b", "評価: jqara").char).toBe("J");
    expect(kbGlyph("c", "  ").char).toBe("・");
  });
  it("色は id から決まり、同じ id なら毎回同じ", () => {
    const g = kbGlyph("kb-123", "仕様書");
    expect(GLYPH_COLORS).toContain(g.color);
    expect(kbGlyph("kb-123", "名前を変えた").color).toBe(g.color);
  });
});

describe("suggestionsFrom（首ページの質問の候補）", () => {
  const doc = (id: string, filename: string) => ({ id, filename });
  it("よく引用される文書から 3 件まで作る", () => {
    const out = suggestionsFrom({
      top_cited: [doc("1", "x01-部品台帳.xlsx"), doc("2", "w03-手順書.docx"), doc("3", "a.pdf"), doc("4", "b.pdf")].map((document) => ({ document })),
      recent: [],
    });
    expect(out).toHaveLength(3);
    expect(out[0]).toEqual({ id: "1", filename: "x01-部品台帳.xlsx", text: "「x01-部品台帳」の内容を要約してください" });
    expect(out[1].text).toBe("「w03-手順書」の要点を教えてください");
  });
  it("引用がまだ無ければ最近の文書から作り、同じ文書は重ねない", () => {
    const out = suggestionsFrom({ top_cited: [{ document: doc("1", "a.md") }], recent: [doc("1", "a.md"), doc("2", "b.md")] });
    expect(out.map((s) => s.id)).toEqual(["1", "2"]);
  });
  it("文書が無ければ空", () => {
    expect(suggestionsFrom({ top_cited: [], recent: [] })).toEqual([]);
    expect(suggestionsFrom(null)).toEqual([]);
  });
});

describe("matchesQuery（コマンドパレットの絞り込み）", () => {
  it("大文字小文字・全角半角を区別せず、空白区切りの語をすべて含むものに合う", () => {
    expect(matchesQuery("MX-17 の部品はいつ届く？", "mx-17 部品")).toBe(true);
    expect(matchesQuery("ＭＸ－１７ の部品", "mx-17")).toBe(true);
    expect(matchesQuery("設定を開く", "ヘルプ")).toBe(false);
    expect(matchesQuery("なんでも", "  ")).toBe(true);
  });
});
