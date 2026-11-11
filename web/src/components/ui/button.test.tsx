import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { Button, IconButton, buttonVariants } from "@/components/ui/button";

describe("buttonVariants", () => {
  it("既定は secondary・md", () => {
    expect(buttonVariants()).toBe(buttonVariants({ variant: "secondary", size: "md" }));
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
