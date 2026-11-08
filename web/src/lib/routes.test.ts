import { describe, expect, it } from "vitest";
import { parseRoute, routePath, type Route } from "@/lib/routes";

describe("routes", () => {
  it("URL を画面に写す", () => {
    expect(parseRoute("/")).toEqual({ view: "chat", threadId: null });
    expect(parseRoute("/c/t%201")).toEqual({ view: "chat", threadId: "t 1" });
    expect(parseRoute("/library")).toEqual({ view: "library", kbId: null });
    expect(parseRoute("/library/kb1")).toEqual({ view: "library", kbId: "kb1" });
    expect(parseRoute("/trash")).toEqual({ view: "trash" });
    expect(parseRoute("/unknown")).toEqual({ view: "chat", threadId: null });
  });

  it("往復しても同じ画面になる", () => {
    const all: Route[] = [
      { view: "chat", threadId: null },
      { view: "chat", threadId: "a/b" },
      { view: "library", kbId: null },
      { view: "library", kbId: "k" },
      { view: "trash" },
    ];
    for (const r of all) expect(parseRoute(routePath(r))).toEqual(r);
  });
});
