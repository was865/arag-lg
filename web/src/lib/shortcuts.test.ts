import { describe, expect, it } from "vitest";
import { SHORTCUT_GROUPS, shortcutAction } from "@/lib/shortcuts";

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

  it("⌘,（Ctrl+,）で設定を開く", () => {
    expect(shortcutAction(key(",", { metaKey: true }), { running: false })).toBe("open-settings");
    expect(shortcutAction(key(",", { ctrlKey: true }), { running: true })).toBe("open-settings");
  });

  it("? でヘルプ。入力中は文字として扱う", () => {
    expect(shortcutAction(key("?", { shiftKey: true }), { running: false })).toBe("open-help");
    expect(shortcutAction(key("?", { shiftKey: true }), { running: false, editing: true })).toBeNull();
  });

  it("一覧はキー判定と同じ表記を使う", () => {
    const keys = SHORTCUT_GROUPS.flatMap((g) => g.items.map((i) => i.keys));
    expect(keys).toContain("⇧⌘O");
    expect(keys).toContain("⌘,");
    expect(keys).toContain("?");
  });

  it("修飾キーなし・IME 変換中は何もしない", () => {
    expect(shortcutAction(key("b"), { running: false })).toBeNull();
    expect(shortcutAction(key("b", { metaKey: true, isComposing: true }), { running: false })).toBeNull();
  });
});
