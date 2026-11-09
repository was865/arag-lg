import { describe, expect, it } from "vitest";
import { parseSectionBody } from "@/components/sources/parse-section-body";

describe("parseSectionBody", () => {
  it("プレーンテキストは 1 つの text セグメント", () => {
    expect(parseSectionBody("ただの本文")).toEqual([{ kind: "text", text: "ただの本文" }]);
  });

  it("空文字は空配列", () => {
    expect(parseSectionBody("   ")).toEqual([]);
  });

  it("表のみ", () => {
    const html = "<table><tr><td>A</td></tr></table>";
    expect(parseSectionBody(html)).toEqual([{ kind: "table", html }]);
  });

  it("画像のみ（src と alt を取り出す）", () => {
    expect(parseSectionBody("![冷却図](/api/documents/d/assets/images/a.jpg)")).toEqual([
      { kind: "image", alt: "冷却図", src: "/api/documents/d/assets/images/a.jpg" },
    ]);
  });

  it("テキスト→画像→テキストの順序を保つ", () => {
    const segs = parseSectionBody("前\n![](/x/a.jpg)\n後");
    expect(segs).toEqual([
      { kind: "text", text: "前" },
      { kind: "image", alt: "", src: "/x/a.jpg" },
      { kind: "text", text: "後" },
    ]);
  });

  it("テキストと表の混在", () => {
    const segs = parseSectionBody("見出し\n<table><tr><td>A</td></tr></table>");
    expect(segs).toEqual([
      { kind: "text", text: "見出し" },
      { kind: "table", html: "<table><tr><td>A</td></tr></table>" },
    ]);
  });

  it("mermaid フェンスを mermaid セグメントとして取り出す", () => {
    const segs = parseSectionBody("```mermaid\ngraph LR\n  A-->B\n```");
    expect(segs).toEqual([{ kind: "mermaid", code: "graph LR\n  A-->B" }]);
  });

  it("閉じフェンスが後続テキストに密着していても分割する（実データ形）", () => {
    const body = "図1: 冷却ライン\n```mermaid\ngraph LR\n  A[\"P-04\"]-->B[\"HX-7\"]\n```一次対応の説明";
    expect(parseSectionBody(body)).toEqual([
      { kind: "text", text: "図1: 冷却ライン" },
      { kind: "mermaid", code: 'graph LR\n  A["P-04"]-->B["HX-7"]' },
      { kind: "text", text: "一次対応の説明" },
    ]);
  });

  it("Markdown の表（docling の出力）を表にする", () => {
    const body = [
      "表1: 点検表A（1/2）",
      "",
      "| 設備ID   |   振動 | 補足       |",
      "|--------|------|----------|",
      "| MX-17  | 0.91 | 軸受け交換が必要 |",
      "| MX-21  | 0.49 | a \\| b <x> & c |",
      "",
      "続きの本文",
    ].join("\n");
    expect(parseSectionBody(body)).toEqual([
      { kind: "text", text: "表1: 点検表A（1/2）" },
      {
        kind: "table",
        html:
          "<table><thead><tr><th>設備ID</th><th>振動</th><th>補足</th></tr></thead><tbody>" +
          "<tr><td>MX-17</td><td>0.91</td><td>軸受け交換が必要</td></tr>" +
          "<tr><td>MX-21</td><td>0.49</td><td>a | b &lt;x&gt; &amp; c</td></tr>" +
          "</tbody></table>",
      },
      { kind: "text", text: "続きの本文" },
    ]);
  });

  it("区切り行の無い | 始まりの行は表にしない", () => {
    expect(parseSectionBody("| ただの引用 |\n| 次の行 |")).toEqual([
      { kind: "text", text: "| ただの引用 |\n| 次の行 |" },
    ]);
  });

  it("途中で切れた表（抜粋の上限）も、そろった行までを表にする", () => {
    const body = "| A | B |\n|---|:-:|\n| 1 | 2 |\n| 3 | 4";
    expect(parseSectionBody(body)).toEqual([
      {
        kind: "table",
        html: "<table><thead><tr><th>A</th><th>B</th></tr></thead><tbody><tr><td>1</td><td>2</td></tr><tr><td>3</td><td>4</td></tr></tbody></table>",
      },
    ]);
  });
});
