import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";
import { TipCarousel } from "@/components/chat/tip-carousel";
import type { UsageTip } from "@/lib/types";

const TIPS: UsageTip[] = [
  { icon: "search", title: "提出具体的问题", body: "指明文档、时间或对比对象，检索更准。", fill: "对比A和B" },
  { icon: "spark", title: "用「技能」一键产出", body: "选技能直接生成报告。", fill: "提取决议" },
];

test("TipCarousel は最初のヒントの見出しと本文を描画する", () => {
  const html = renderToStaticMarkup(
    createElement(TipCarousel, { tips: TIPS, onFill: () => {} }),
  );
  expect(html).toContain("提出具体的问题");
  expect(html).toContain("指明文档、时间或对比对象，检索更准。");
});

test("TipCarousel は tips が空なら何も描画しない", () => {
  const html = renderToStaticMarkup(
    createElement(TipCarousel, { tips: [], onFill: () => {} }),
  );
  expect(html).toBe("");
});

test("TipCarousel は複数 tip で件数分のドットを描画する", () => {
  const html = renderToStaticMarkup(
    createElement(TipCarousel, { tips: TIPS, onFill: () => {} }),
  );
  // 各ドットは aria-label にヒント見出しを持つ。
  expect(html).toContain('aria-label="提出具体的问题"');
  expect(html).toContain('aria-label="用「技能」一键产出"');
});

test("TipCarousel はヒント本文の長さでカード高さが変わらない寸法を持つ", () => {
  const html = renderToStaticMarkup(
    createElement(TipCarousel, { tips: TIPS, onFill: () => {} }),
  );
  expect(html).toContain("h-[224px]");
  expect(html).toContain("max-md:h-[232px]");
  expect(html).toContain("h-[42px]");
  expect(html).toContain("[-webkit-line-clamp:2]");
});
