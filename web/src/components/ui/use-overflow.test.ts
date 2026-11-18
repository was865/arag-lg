import { describe, expect, it } from "vitest";
import { computeOverflow } from "@/components/ui/use-overflow";

describe("computeOverflow", () => {
  it("はみ出しが無ければ両方 false", () => {
    expect(computeOverflow({ scrollLeft: 0, scrollWidth: 300, clientWidth: 300 })).toMatchObject({ left: false, right: false });
  });

  it("先頭ではみ出しがあれば right のみ true", () => {
    expect(computeOverflow({ scrollLeft: 0, scrollWidth: 500, clientWidth: 300 })).toMatchObject({ left: false, right: true });
  });

  it("中間までスクロールすると両側 true", () => {
    expect(computeOverflow({ scrollLeft: 100, scrollWidth: 500, clientWidth: 300 })).toMatchObject({ left: true, right: true });
  });

  it("末尾までスクロールすると left のみ true", () => {
    expect(computeOverflow({ scrollLeft: 200, scrollWidth: 500, clientWidth: 300 })).toMatchObject({ left: true, right: false });
  });

  it("1px 未満の端数は許容する", () => {
    expect(computeOverflow({ scrollLeft: 0.5, scrollWidth: 300.4, clientWidth: 300 })).toMatchObject({ left: false, right: false });
  });
  it("縦の続き", () => {
    const m = { scrollLeft: 0, scrollWidth: 200, clientWidth: 200, clientHeight: 300, scrollHeight: 500 };
    expect(computeOverflow({ ...m, scrollTop: 0 })).toEqual({ top: false, bottom: true, left: false, right: false });
    expect(computeOverflow({ ...m, scrollTop: 100 })).toMatchObject({ top: true, bottom: true });
    expect(computeOverflow({ ...m, scrollTop: 200 })).toMatchObject({ top: true, bottom: false });
  });
});
