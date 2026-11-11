/**
 * 動きの値（specs/025-ui-motion）。globals.css の @theme と同じ値を置く（motion.test.ts で一致を確かめる）。
 * CSS で動かすものは animate-* / ease-* のクラスを、Motion で動かすものはこの定数を使う。
 */

/** 秒。速い = ホバー・押下、中 = メニュー・カード、遅い = ダイアログ・画面の切り替え、exit = 消えるとき */
export const DURATION = { fast: 0.12, mid: 0.2, slow: 0.32, exit: 0.14 } as const;

/** 3 次ベジェの制御点。spring = 出るとき（少し行き過ぎて戻る）、out = 淡く現れるだけ、in = 消えるとき */
export const EASE = {
  spring: [0.3, 1.3, 0.5, 1],
  out: [0.2, 0.8, 0.2, 1],
  in: [0.4, 0, 1, 1],
} as const;

/** Motion のばね。CSS の --ease-spring と見た目を合わせた値 */
export const SPRING = { type: "spring", stiffness: 520, damping: 38, mass: 0.9 } as const;

/** 束で見せるトーストの数（それより古いものは隠す） */
export const TOAST_VISIBLE = 3;

/**
 * トーストの束での位置。index は新しい順（0 = いちばん新しい）。
 * 閉じた束では古いものほど上へずれて縮み、広げた束では原寸で縦に並べる。
 */
export function stackStyle(index: number, expanded: boolean, height = 48) {
  if (expanded) return { y: -(height + 8) * index, scale: 1, opacity: 1, hidden: false };
  if (index >= TOAST_VISIBLE) return { y: -14 * TOAST_VISIBLE, scale: 1 - 0.05 * TOAST_VISIBLE, opacity: 0, hidden: true };
  return { y: index === 0 ? 0 : -14 * index, scale: 1 - 0.05 * index, opacity: 1 - 0.18 * index, hidden: false };
}
