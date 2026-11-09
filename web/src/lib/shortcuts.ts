/** 画面全体のキーボード操作。⌘ は Windows・Linux では Ctrl として扱う。
 *
 * ⌘N はブラウザの新規ウィンドウに取られて止められないので、新規スレッドは ⇧⌘O（一般的なチャット UI と同じ）。
 */
export type ShortcutAction = "new-thread" | "toggle-sidebar" | "stop" | "open-settings";

type KeyLike = Pick<KeyboardEvent, "key" | "metaKey" | "ctrlKey" | "shiftKey" | "altKey" | "isComposing">;

export function shortcutAction(e: KeyLike, { running }: { running: boolean }): ShortcutAction | null {
  if (e.isComposing || e.altKey) return null;
  const mod = e.metaKey || e.ctrlKey;
  if (!mod) return null;
  const key = e.key.toLowerCase();
  if (e.shiftKey && key === "o") return "new-thread";
  if (!e.shiftKey && key === "b") return "toggle-sidebar";
  if (!e.shiftKey && key === "backspace" && running) return "stop";
  if (!e.shiftKey && key === ",") return "open-settings";
  return null;
}

/** 表示用の表記（Mac 以外は Ctrl）。 */
export const SHORTCUT_LABEL = {
  newThread: "⇧⌘O",
  stop: "⌘⌫",
  settings: "⌘,",
} as const;
