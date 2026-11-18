import { describe, expect, it } from "vitest";
import { linkHandlers, linkMarks } from "@/components/ui/link-marks";

/** querySelectorAll と closest だけを持つ小さな偽の要素 */
function fakeTree() {
  const attrs = new Map<string, Set<string>>();
  const el = (id: string) => ({
    id,
    setAttribute: (k: string) => attrs.set(id, new Set([...(attrs.get(id) ?? []), k])),
    removeAttribute: (k: string) => attrs.get(id)?.delete(k),
  });
  const a = el("a");
  const b = el("b");
  const root = { querySelectorAll: (sel: string) => (sel === "[data-k='1']" ? [a, b] : []) };
  const from = { closest: (scope: string) => (scope === "[data-scope]" ? root : null) } as unknown as Element;
  return { from, on: (id: string) => attrs.get(id)?.has("data-on") ?? false };
}

describe("linkMarks", () => {
  it("同じ鍵の要素をまとめて光らせ、消す", () => {
    const t = fakeTree();
    linkMarks(t.from, "[data-scope]", "[data-k='1']", true);
    expect(t.on("a") && t.on("b")).toBe(true);
    linkMarks(t.from, "[data-scope]", "[data-k='1']", false);
    expect(t.on("a") || t.on("b")).toBe(false);
  });
  it("scope の外では何もしない", () => {
    const t = fakeTree();
    linkMarks(t.from, "[data-other]", "[data-k='1']", true);
    expect(t.on("a")).toBe(false);
  });
  it("ホバーとフォーカスの出入りを 1 つの関数にまとめる", () => {
    const calls: boolean[] = [];
    const h = linkHandlers((_, on) => calls.push(on));
    const e = { currentTarget: {} as Element };
    h.onPointerEnter(e);
    h.onPointerLeave(e);
    h.onFocus(e);
    h.onBlur(e);
    expect(calls).toEqual([true, false, true, false]);
  });
});
