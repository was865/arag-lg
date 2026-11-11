import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { Segmented } from "@/components/ui/segmented";

const OPTIONS = [
  ["all", "すべて"],
  ["running", "処理中"],
  ["failed", "失敗"],
] as const;

function render(value: (typeof OPTIONS)[number][0]) {
  return renderToStaticMarkup(<Segmented label="状態" value={value} options={OPTIONS} onChange={() => {}} />);
}

describe("Segmented", () => {
  it("選択肢は radio として読み上げる", () => {
    const html = render("running");
    expect(html).toContain('role="radiogroup"');
    expect(html).toContain('aria-label="状態"');
    expect(html.match(/aria-checked="true"/g)).toHaveLength(1);
  });
  it("滑る背景は選択中の選択肢の中に 1 つだけある", () => {
    const html = render("running");
    expect(html.match(/data-segmented-thumb/g)).toHaveLength(1);
    const checked = html.slice(html.indexOf('aria-checked="true"'));
    expect(checked.indexOf("data-segmented-thumb")).toBeLessThan(checked.indexOf("</button>"));
  });
});
