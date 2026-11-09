/** スレッドの共有（specs/008-thread-share）。 */
import type { IconName } from "@/components/icons";

export type Visibility = "private" | "org" | "public";

export const VISIBILITY_OPTIONS: { id: Visibility; iconName: IconName; label: string; desc: string }[] = [
  { id: "private", iconName: "lock", label: "自分のみ", desc: "リンクを知っていても開けません" },
  { id: "org", iconName: "group", label: "社内", desc: "ログインしている利用者が読めます" },
  { id: "public", iconName: "link", label: "リンクを知っている人", desc: "ログインしていない人も読めます" },
];

/** 共有リンク。private やトークンが無いときは null（リンクを出さない）。 */
export function shareUrl(origin: string, visibility: Visibility, token: string | null | undefined): string | null {
  if (visibility === "private" || !token) return null;
  return `${origin.replace(/\/$/, "")}/s/${encodeURIComponent(token)}`;
}
