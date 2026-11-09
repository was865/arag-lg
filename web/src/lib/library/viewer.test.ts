import { describe, expect, it } from "vitest";
import { activeSectionId, outlineIndent, pipeTablesToHtml, resolveAssets } from "@/lib/library/viewer";

describe("resolveAssets", () => {
  it("assets/ の画像を文書の API に向け、それ以外はそのまま", () => {
    const t = "図: ![配線図](assets/fig-1.png) と ![外部](https://x/y.png)";
    expect(resolveAssets(t, "d 1")).toBe("図: ![配線図](/api/v1/documents/d%201/assets/fig-1.png) と ![外部](https://x/y.png)");
  });
});

describe("outlineIndent", () => {
  it("最も浅い見出しを 0 とした字下げ（最大 4）", () => {
    expect(outlineIndent([{ level: 2 }, { level: 3 }, { level: 2 }, { level: 9 }])).toEqual([0, 1, 0, 4]);
    expect(outlineIndent([])).toEqual([]);
  });
});

describe("activeSectionId", () => {
  const tops = [
    { id: "a", top: 0 },
    { id: "b", top: 400 },
    { id: "c", top: 900 },
  ];
  it("画面上端（余白つき）を越えた最後の章", () => {
    expect(activeSectionId(tops, 0)).toBe("a");
    expect(activeSectionId(tops, 350)).toBe("b");
    expect(activeSectionId(tops, 2000)).toBe("c");
    expect(activeSectionId([], 10)).toBeNull();
  });
});

describe("pipeTablesToHtml", () => {
  it("区切り行のある | 表を <table> にし、前後の文はそのまま", () => {
    const md = "表1:\n| ID | 値 |\n|----|---:|\n| a<b | 1 |\n| c |  |\n後の文";
    expect(pipeTablesToHtml(md)).toBe(
      "表1:\n<table><thead><tr><th>ID</th><th>値</th></tr></thead><tbody><tr><td>a&lt;b</td><td>1</td></tr><tr><td>c</td><td></td></tr></tbody></table>\n後の文",
    );
  });
  it("区切り行が無ければ変えない", () => {
    expect(pipeTablesToHtml("| a | b |\n| c | d |")).toBe("| a | b |\n| c | d |");
  });
});
