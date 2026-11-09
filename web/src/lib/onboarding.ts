/** 初回ガイド（specs/015-help-onboarding R5）。この端末に利用者ごとに「見た」を記録する。 */

export const guideKey = (userId: string) => `arag:onboarded:${userId}`;

export function shouldShowGuide({ userId, seen }: { userId: string | null | undefined; seen: string | null }): boolean {
  return Boolean(userId) && !seen;
}

export const GUIDE_STEPS: { icon: "folder" | "search" | "doc" | "cog"; title: string; body: string }[] = [
  {
    icon: "folder",
    title: "文書を追加する",
    body: "サイドバーのナレッジベースを開き「追加」から、ファイルやフォルダを追加します。取り込みが終わるとすぐ質問に使えます。",
  },
  {
    icon: "search",
    title: "範囲を選んで質問する",
    body: "入力欄の左で、すべての文書・ナレッジベース・1 つの文書から範囲を選び、ふだんの言葉で質問します。",
  },
  {
    icon: "doc",
    title: "出典で確かめる",
    body: "回答の [1] [2] を押すと、右のパネルで原文の該当箇所が開きます。資料に無いことは「見つからない」と答えます。",
  },
  {
    icon: "cog",
    title: "設定とヘルプ",
    body: "左下のメニューから設定（⌘,）とヘルプ（?）を開けます。このガイドはヘルプからもう一度見られます。",
  },
];
