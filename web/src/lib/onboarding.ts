/** 初回ガイド（specs/015-help-onboarding R5）。旧版のスポットライトツアーを移植し、新版の画面に合わせた。
 *  DOM に依存しない部分（ステップ定義・スポットライト矩形・ポップオーバー配置・表示判定）。 */

export const guideKey = (userId: string) => `arag:onboarded:${userId}`;

export function shouldShowGuide({ userId, seen }: { userId: string | null | undefined; seen: string | null }): boolean {
  return Boolean(userId) && !seen;
}

/** 各 id は画面側の `data-tour` 属性と対応する。対象が見えないとき（375px でサイドバーが閉じている等）は
 *  ステップを飛ばさず、スポットライト無しのカードで説明する。 */
export const TOUR_STEPS = [
  {
    id: "kb-section",
    title: "ナレッジベース",
    body: "文書はナレッジベースごとに管理します。開いて「追加」からファイルやフォルダを追加すると、取り込みが終わりしだい質問に使えます。",
  },
  {
    id: "scope",
    title: "検索の範囲",
    body: "すべての文書・ナレッジベース・1 つの文書から、どこを調べるかを選べます。関係する範囲に絞ると速く正確になります。",
  },
  {
    id: "composer",
    title: "質問する",
    body: "ふだんの言葉で質問します。回答の [1] [2] を押すと、右のパネルで原文の該当箇所を確かめられます。",
  },
  {
    id: "user-menu",
    title: "設定とヘルプ",
    body: "ここから設定（⌘,）とヘルプ（?）を開けます。このガイドはヘルプからもう一度見られます。",
  },
] as const;
export type TourStepId = (typeof TOUR_STEPS)[number]["id"];

export interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

const SPOT_PADDING = 8;
const POPOVER_GAP = 12;
const VIEWPORT_MARGIN = 16;

/** 対象が画面内に見えているか（幅 0・画面外へ退避したサイドバーは見えていない扱い）。 */
export function isVisibleRect(r: Rect | null, viewport: { width: number; height: number }): r is Rect {
  if (!r || r.width <= 0 || r.height <= 0) return false;
  return r.left < viewport.width && r.left + r.width > 0 && r.top < viewport.height && r.top + r.height > 0;
}

/** 対象にパディングを付けたスポットライト。負座標は 0 に丸める（その分反対側へは広げない）。 */
export function spotlightRect(target: Rect): Rect {
  const left = Math.max(0, target.left - SPOT_PADDING);
  const top = Math.max(0, target.top - SPOT_PADDING);
  return {
    left,
    top,
    width: target.left + target.width + SPOT_PADDING - left,
    height: target.top + target.height + SPOT_PADDING - top,
  };
}

/** スポットライトの下（空きが無ければ上）にポップオーバーを置き、画面内に収める。 */
export function placePopover(
  spot: Rect,
  popover: { width: number; height: number },
  viewport: { width: number; height: number },
): { side: "top" | "bottom"; top: number; left: number } {
  const fitsBelow = spot.top + spot.height + POPOVER_GAP + popover.height + VIEWPORT_MARGIN <= viewport.height;
  const side = fitsBelow ? "bottom" : "top";
  const rawTop = fitsBelow ? spot.top + spot.height + POPOVER_GAP : spot.top - POPOVER_GAP - popover.height;
  const maxTop = viewport.height - VIEWPORT_MARGIN - popover.height;
  const top = Math.min(Math.max(rawTop, VIEWPORT_MARGIN), maxTop);
  const centered = spot.left + spot.width / 2 - popover.width / 2;
  const maxLeft = viewport.width - VIEWPORT_MARGIN - popover.width;
  const left = Math.min(Math.max(centered, VIEWPORT_MARGIN), maxLeft);
  return { side, top, left };
}
