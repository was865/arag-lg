import { describe, it, expect } from "vitest";
import { remarkCitations, __test } from "@/components/chat/remark-citations";

const { splitCitations, transform } = __test;

describe("splitCitations", () => {
  it("素の [N] を #cite-N の link ノードへ変換する", () => {
    const out = splitCitations("結論です [1]。");
    expect(out).toEqual([
      { type: "text", value: "結論です " },
      { type: "link", url: "#cite-1", children: [{ type: "text", value: "1" }] },
      { type: "text", value: "。" },
    ]);
  });

  it("連続する引用 [1][2] を個別の link ノードへ分解する", () => {
    const out = splitCitations("根拠 [1][2]");
    expect(out.filter((n) => n.type === "link").map((n) => n.url)).toEqual(["#cite-1", "#cite-2"]);
  });

  it("gpt-5-mini が出しやすい全角引用記号も link ノードへ分解する", () => {
    const out = splitCitations("根拠【4】と補足［5］");
    expect(out.filter((n) => n.type === "link").map((n) => n.url)).toEqual(["#cite-4", "#cite-5"]);
  });
});

describe("remarkCitations transform", () => {
  it("text ノードのみ走査し link 内の [N] は変換しない", () => {
    // mdast 風ツリー: paragraph[ text, link[ text "[9]" ] ]
    const tree = {
      type: "root",
      children: [
        {
          type: "paragraph",
          children: [
            { type: "text", value: "本文 [3]" },
            { type: "link", url: "https://x.test", children: [{ type: "text", value: "[9]" }] },
          ],
        },
      ],
    };
    remarkCitations()(tree);
    const para = tree.children[0];
    // "本文 [3]" は text + cite link に分解される。
    const kinds = para.children.map((n) => `${n.type}:${n.url ?? n.value ?? ""}`);
    expect(kinds).toContain("link:#cite-3");
    // 既存リンクは保持され、その子 "[9]" は cite link 化されない。
    const existingLink = para.children.find((n) => n.url === "https://x.test")!;
    expect(existingLink.children).toEqual([{ type: "text", value: "[9]" }]);
  });

  it("引用が無いツリーは変更しない（link を増やさない）", () => {
    const tree = {
      type: "root",
      children: [{ type: "paragraph", children: [{ type: "text", value: "ただの本文" }] }],
    };
    transform(tree);
    expect(tree.children[0].children).toEqual([{ type: "text", value: "ただの本文" }]);
  });
});
