import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { Badge, badgeVariants } from "@/components/ui/badge";

describe("Badge", () => {
  it("既定は塗りの中立色・mini の文字", () => {
    const cls = badgeVariants();
    expect(cls).toContain("bg-divider");
    expect(cls).toContain("text-mini");
    expect(cls).toContain("rounded-full");
  });
  it("tone ごとに色が変わる", () => {
    expect(badgeVariants({ tone: "outline" })).toContain("border-divider-strong");
    expect(badgeVariants({ tone: "accent" })).toContain("bg-accent-soft");
    expect(badgeVariants({ tone: "solid" })).toContain("bg-accent");
    expect(badgeVariants({ tone: "danger" })).toContain("text-danger");
  });
  it("mono で等幅・大文字の状態表示になる", () => {
    expect(badgeVariants({ mono: true })).toContain("font-mono");
  });
  it("span として描き、追加のクラスを足せる", () => {
    const html = renderToStaticMarkup(<Badge className="ml-2">閲覧のみ</Badge>);
    expect(html).toMatch(/^<span class="[^"]*ml-2[^"]*">閲覧のみ<\/span>$/);
  });
});
