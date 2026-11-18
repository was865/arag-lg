import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { Card } from "@/components/ui/card";
import { FileTile } from "@/components/ui/file-tile";
import { Spinner } from "@/components/ui/spinner";

describe("Card（面）", () => {
  it("tone で面を選び、使う側の class を足せる", () => {
    expect(renderToStaticMarkup(<Card className="p-3">x</Card>)).toContain('class="card p-3"');
    expect(renderToStaticMarkup(<Card tone="sunken" />)).toContain("card-sunken");
    expect(renderToStaticMarkup(<Card tone="linked" />)).toContain("data-[on]:border-accent");
  });
  it("asChild で要素を差し替える（ボタン・section など）", () => {
    const html = renderToStaticMarkup(
      <Card asChild tone="raised">
        <button type="button">押す</button>
      </Card>,
    );
    expect(html).toMatch(/^<button type="button" class="card-raised">/);
  });
});

describe("Spinner（回る輪）", () => {
  it("文字があれば読み上げ、無ければ隠す", () => {
    expect(renderToStaticMarkup(<Spinner label="実行中" />)).toContain('role="status" aria-label="実行中"');
    expect(renderToStaticMarkup(<Spinner />)).toContain('aria-hidden="true"');
  });
  it("動きを減らす設定では回さない", () => {
    expect(renderToStaticMarkup(<Spinner />)).toContain("motion-reduce:animate-none");
  });
});

describe("FileTile（形式の札）", () => {
  it("ファイル名から形式の色を敷く", () => {
    const html = renderToStaticMarkup(<FileTile filename="手順書.pdf" />);
    expect(html).toContain("color-mix(in srgb");
  });
  it("色が無ければ灰色の面にする", () => {
    const html = renderToStaticMarkup(<FileTile icon="folder" />);
    expect(html).toContain("bg-surface-2");
  });
});
