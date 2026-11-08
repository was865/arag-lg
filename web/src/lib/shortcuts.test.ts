import { describe, expect, it } from "vitest";
import { shortcutAction } from "@/lib/shortcuts";

const key = (k: string, over: Partial<KeyboardEvent> = {}) =>
  ({ key: k, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false, isComposing: false, ...over }) as KeyboardEvent;

describe("shortcutAction", () => {
  it("⇧⌘O（Ctrl+Shift+O）で新規スレッド", () => {
    expect(shortcutAction(key("O", { metaKey: true, shiftKey: true }), { running: false })).toBe("new-thread");
    expect(shortcutAction(key("o", { ctrlKey: true, shiftKey: true }), { running: false })).toBe("new-thread");
  });

  it("⌘B でサイドバー、⌘⌫ は生成中だけ停止", () => {
    expect(shortcutAction(key("b", { metaKey: true }), { running: false })).toBe("toggle-sidebar");
    expect(shortcutAction(key("Backspace", { metaKey: true }), { running: true })).toBe("stop");
    expect(shortcutAction(key("Backspace", { metaKey: true }), { running: false })).toBeNull();
  });

  it("修飾キーなし・IME 変換中は何もしない", () => {
    expect(shortcutAction(key("b"), { running: false })).toBeNull();
    expect(shortcutAction(key("b", { metaKey: true, isComposing: true }), { running: false })).toBeNull();
  });
});
