/**
 * 互いに光る印とカード（specs/025 R45 の「回答の印 ↔ 根拠カード」を部品にしたもの）。
 * - 同じ鍵を持つ要素（印・カード・枠）を、ホバー・フォーカスで一緒に光らせる。
 * - 連動は DOM の属性 `data-on` を切り替えるだけにし、React の状態を持たない（大きな一覧や描き直しの重い本文でも軽い）。
 * - 光り方は `data-[on]:` で書く。カードは `Card tone="linked"`（ui/card）を使う。
 * サーバーからも読み込めるよう hook を使わない。
 */

/** from を含む scope（CSS セレクタ）の中で、selector に合う要素を光らせる（消す）。 */
export function linkMarks(from: Element, scope: string, selector: string, on: boolean): void {
  const root = from.closest(scope);
  if (!root) return;
  for (const el of root.querySelectorAll(selector)) {
    if (on) el.setAttribute("data-on", "");
    else el.removeAttribute("data-on");
  }
}

/** ホバー・フォーカスの出入りで link を呼ぶ props（ボタン・行にそのまま渡す）。 */
export function linkHandlers(link: (from: Element, on: boolean) => void) {
  const h = (on: boolean) => (e: { currentTarget: Element }) => link(e.currentTarget, on);
  return { onPointerEnter: h(true), onPointerLeave: h(false), onFocus: h(true), onBlur: h(false) };
}
