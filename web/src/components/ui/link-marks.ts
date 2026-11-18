/**
 * 互いに光る印とカード（specs/025 R45 の「回答の印 ↔ 根拠カード」を部品にしたもの）。
 * - 同じ鍵を持つ要素（印・カード・枠）を、ホバー・フォーカスで一緒に光らせる。
 * - 連動は DOM の属性 `data-on` を切り替えるだけにし、React の状態を持たない（大きな一覧や描き直しの重い本文でも軽い）。
 * - 光り方は `data-[on]:` で書く。カードは `linkedCard` を使う（印は回答の引用の印 `CitationButton` を参照）。
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

/** 光るカード（根拠カードと同じ見た目）。中身の並びと幅は呼び出し側で足す。 */
export const linkedCard =
  "rounded-card border-[0.5px] border-divider-strong bg-surface shadow-e1 outline-none transition-[transform,box-shadow,border-color] duration-(--duration-mid) ease-out hover:shadow-e2 focus-visible:ring-2 focus-visible:ring-accent/50 data-[on]:border-accent data-[on]:shadow-[0_0_0_3px_var(--accent-soft),var(--shadow-2)] motion-reduce:transition-none";
