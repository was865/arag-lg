import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { Button, IconButton, buttonVariants } from "@/components/ui/button";

describe("buttonVariants", () => {
  it("既定は secondary・md", () => {
    expect(buttonVariants()).toBe(buttonVariants({ variant: "secondary", size: "md" }));
  });
  it("押すとわずかに縮む（視差効果を減らす設定では縮まない）", () => {
    const cls = buttonVariants();
    expect(cls).toContain("active:scale-[0.97]");
    expect(cls).toContain("motion-reduce:active:scale-100");
  });
  it("primary は墨色（朱は引用の印と送信に取っておく）", () => {
    const cls = buttonVariants({ variant: "primary" });
    expect(cls).toContain("bg-fg");
    expect(cls).toContain("text-bg");
    expect(cls).not.toContain("bg-accent");
  });
  it("danger-ghost は塗りなしの赤い文字", () => {
    const cls = buttonVariants({ variant: "danger-ghost" });
    expect(cls).toContain("text-danger");
    expect(cls).toContain("hover:bg-danger-soft");
    expect(cls).not.toContain("bg-danger ");
  });
});

describe("Button", () => {
  it("type の既定は button（フォームを誤って送らない）", () => {
    expect(renderToStaticMarkup(<Button>保存</Button>)).toContain('type="button"');
  });
});

describe("IconButton", () => {
  it("label を読み上げ名とツールチップに使う", () => {
    const html = renderToStaticMarkup(<IconButton label="閉じる" icon="close" />);
    expect(html).toContain('aria-label="閉じる"');
    expect(html).toContain('title="閉じる"');
  });
  it("tooltip={false} ならツールチップを付けない", () => {
    const html = renderToStaticMarkup(<IconButton label="閉じる" icon="close" tooltip={false} />);
    expect(html).toContain('aria-label="閉じる"');
    expect(html).not.toContain("title=");
  });
});
