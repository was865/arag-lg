import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { Input, SearchField, Select, Textarea, inputVariants } from "@/components/ui/input";

describe("inputVariants", () => {
  it("大きさごとに高さと文字の段階が決まる", () => {
    expect(inputVariants({ size: "sm" })).toContain("h-7");
    expect(inputVariants({ size: "sm" })).toContain("text-footnote");
    expect(inputVariants({ size: "md" })).toContain("h-8");
    expect(inputVariants({ size: "lg" })).toContain("h-9");
    expect(inputVariants({ size: "xl" })).toContain("h-10");
    expect(inputVariants({ size: "xl" })).toContain("text-callout");
  });
  it("既定は lg（ダイアログのフォーム）", () => {
    expect(inputVariants()).toBe(inputVariants({ size: "lg" }));
  });
});

describe("Input / Select / Textarea", () => {
  it("呼び出し側のクラスを後ろに足せる", () => {
    const html = renderToStaticMarkup(<Input size="md" className="font-mono" />);
    expect(html).toContain("h-8");
    expect(html).toContain("font-mono");
  });
  it("Select と Textarea も同じ見た目になる", () => {
    const sel = renderToStaticMarkup(<Select size="sm"><option>a</option></Select>);
    expect(sel).toContain("h-7");
    // OS の矢印は使わず、自前の矢印と右の余白を持つ
    expect(sel).toContain("appearance-none");
    expect(sel).toContain("select-chevron");
    expect(sel).toContain("pr-7");
    const ta = renderToStaticMarkup(<Textarea rows={2} />);
    expect(ta).toContain("<textarea");
    expect(ta).not.toContain("h-9"); // 複数行は高さを固定しない
  });
});

describe("SearchField", () => {
  it("placeholder を読み上げ名に使う", () => {
    const html = renderToStaticMarkup(<SearchField value="" onChange={() => {}} placeholder="名前で探す" />);
    expect(html).toContain('aria-label="名前で探す"');
  });
  it("値があり onClear があるときだけ消すボタンを出す", () => {
    const empty = renderToStaticMarkup(<SearchField value="" onChange={() => {}} onClear={() => {}} placeholder="探す" />);
    expect(empty).not.toContain("検索語を消す");
    const filled = renderToStaticMarkup(<SearchField value="abc" onChange={() => {}} onClear={() => {}} placeholder="探す" />);
    expect(filled).toContain('aria-label="検索語を消す"');
    const noClear = renderToStaticMarkup(<SearchField value="abc" onChange={() => {}} placeholder="探す" />);
    expect(noClear).not.toContain("検索語を消す");
  });
});
