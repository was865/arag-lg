import { describe, expect, it } from "vitest";
import { sourcesChipLabel } from "@/components/chat/answer-footer";
import type { Source } from "@/lib/types";

const t = { sourcesChip: "出典 {n} 件", sourcesChipDocs: "出典 {n} 件（{docs} 文書）" };
const src = (id: string, n: number): Source => ({
  id,
  type: "doc",
  title: id,
  path: id,
  author: "",
  date: "",
  sections: Array.from({ length: n }, (_, i) => ({ id: `${id}-${i}`, heading: "", body: "" })),
});

describe("sourcesChipLabel", () => {
  it("同じ文書の別箇所も数え、文書数が違えば添える", () => {
    expect(sourcesChipLabel([src("a", 2)], t)).toBe("出典 2 件（1 文書）");
    expect(sourcesChipLabel([src("a", 1), src("b", 1)], t)).toBe("出典 2 件");
  });
  it("引用が無ければ出さない", () => {
    expect(sourcesChipLabel([], t)).toBeNull();
  });
});
