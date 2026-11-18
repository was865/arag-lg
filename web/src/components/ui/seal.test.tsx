import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { Seal, sealClass } from "@/components/ui/seal";

describe("Seal（引用の印）", () => {
  it("番号を朱の四角に入れて出す", () => {
    const html = renderToStaticMarkup(<Seal n={3} />);
    expect(html).toContain(">3<");
    expect(html).toContain("bg-accent");
    expect(html).toContain("text-white");
  });
  it("番号なしは飾り（ブランド印）として読み上げから隠す", () => {
    expect(renderToStaticMarkup(<Seal />)).toContain('aria-hidden="true"');
  });
  it("大きさを選べる", () => {
    expect(sealClass({ size: "sm" })).toContain("h-[15px]");
    expect(sealClass({ size: "md" })).toContain("h-[18px]");
  });
});
