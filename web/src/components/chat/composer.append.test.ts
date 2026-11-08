import { expect, test } from "vitest";
import { appendSnippet } from "@/components/chat/composer";

test("空入力ならそのまま挿入", () => {
  expect(appendSnippet("", "数量：")).toBe("数量：");
  expect(appendSnippet("   ", "数量：")).toBe("数量：");
});

test("既存文の末尾に全角読点で連結", () => {
  expect(appendSnippet("FF100002 现在缺货吗", "数量：")).toBe("FF100002 现在缺货吗，数量：");
});

test("末尾が区切りなら二重の読点を足さない", () => {
  expect(appendSnippet("查一下，", "加急")).toBe("查一下，加急");
  expect(appendSnippet("查一下、", "加急")).toBe("查一下、加急");
  expect(appendSnippet("查一下,", "加急")).toBe("查一下,加急");
});

test("末尾の空白はトリムしてから連結", () => {
  expect(appendSnippet("FF100002  ", "客户：")).toBe("FF100002，客户：");
});
