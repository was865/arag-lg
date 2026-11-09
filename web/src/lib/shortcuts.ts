/** 画面全体のキーボード操作。⌘ は Windows・Linux では Ctrl として扱う。
 *
 * ⌘N はブラウザの新規ウィンドウに取られて止められないので、新規スレッドは ⇧⌘O（一般的なチャット UI と同じ）。
 */
export type ShortcutAction = "new-thread" | "toggle-sidebar" | "stop" | "open-settings" | "open-help";

type KeyLike = Pick<KeyboardEvent, "key" | "metaKey" | "ctrlKey" | "shiftKey" | "altKey" | "isComposing">;

export function shortcutAction(
  e: KeyLike,
  { running, editing = false }: { running: boolean; editing?: boolean },
): ShortcutAction | null {
  if (e.isComposing || e.altKey) return null;
  const mod = e.metaKey || e.ctrlKey;
  // 修飾キーなしのキーは入力欄では文字として扱う
  if (!mod) return !editing && e.key === "?" ? "open-help" : null;
  const key = e.key.toLowerCase();
  if (e.shiftKey && key === "o") return "new-thread";
  if (!e.shiftKey && key === "b") return "toggle-sidebar";
  if (!e.shiftKey && key === "backspace" && running) return "stop";
  if (!e.shiftKey && key === ",") return "open-settings";
  return null;
}

/** フォーカスが文字入力の中にあるか（`?` などを奪わないため）。 */
export function isEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true;
  if (target instanceof HTMLInputElement) {
    return !["checkbox", "radio", "range", "button", "submit", "reset", "file", "color"].includes(target.type);
  }
  return false;
}

/** 表示用の表記（Mac 以外は Ctrl）。 */
export const SHORTCUT_LABEL = {
  newThread: "⇧⌘O",
  stop: "⌘⌫",
  settings: "⌘,",
  sidebar: "⌘B",
  help: "?",
} as const;

/** ヘルプの一覧（specs/015 R3）。shortcutAction と composer が実際に受け付けるキーだけ。 */
export const SHORTCUT_GROUPS: { title: string; items: { keys: string; label: string }[] }[] = [
  {
    title: "基本",
    items: [
      { keys: SHORTCUT_LABEL.newThread, label: "新しいスレッド" },
      { keys: SHORTCUT_LABEL.sidebar, label: "サイドバーを開く・閉じる" },
      { keys: SHORTCUT_LABEL.settings, label: "設定を開く" },
      { keys: SHORTCUT_LABEL.help, label: "ヘルプを開く" },
      { keys: "Esc", label: "パネル・ダイアログを閉じる" },
    ],
  },
  {
    title: "質問",
    items: [
      { keys: "Enter", label: "送信" },
      { keys: "Shift+Enter", label: "改行" },
      { keys: SHORTCUT_LABEL.stop, label: "回答の生成を止める" },
    ],
  },
];
