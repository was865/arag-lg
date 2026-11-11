import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ListSkeleton, TranscriptSkeleton } from "@/components/ui/skeleton";

describe("Skeleton（読み込み中の骨組み）", () => {
  it("一覧は指定した行数を出し、読み上げには「読み込み中」だけを伝える", () => {
    const html = renderToStaticMarkup(<ListSkeleton rows={3} />);
    expect(html.match(/border-b-\[0\.5px\]/g)).toHaveLength(3);
    expect(html).toContain('role="status"');
    expect(html).toContain("読み込み中");
  });
  it("少し遅れて現れる（速い読み込みでちらつかない）", () => {
    expect(renderToStaticMarkup(<ListSkeleton />)).toContain("animate-skeleton-in");
    expect(renderToStaticMarkup(<TranscriptSkeleton />)).toContain("animate-skeleton-in");
  });
});
