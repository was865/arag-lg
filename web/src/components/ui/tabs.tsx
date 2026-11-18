/**
 * タブ（Radix Tabs）。画面の区分の切り替え（設定の種類・文書の表示・管理の区分）はすべてこの見た目にする（specs/025 R47）。
 * 見た目はセグメントと同じ（今いる区分が白い面で浮く）。下線のタブは使わない。
 * - 同じ画面の中で切り替える: Tabs / TabsList / TabsTrigger / TabsContent（←→ で移れる・読み上げにタブと伝わる）
 * - URL ごとに分かれた区分（管理の画面など）: <nav className={tabsListClass}> の中の Link に tabsTriggerClass と aria-current="page"
 * "use client" を付けない（付けると定数の class がサーバーの描画で null になる。Radix は自分で client の境界を持つ）。
 */
import * as T from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";

export const Tabs = T.Root;
export const TabsContent = T.Content;

export const tabsListClass = "inline-flex shrink-0 items-center rounded-control bg-divider p-0.5";

export const tabsTriggerClass =
  "inline-flex h-7 flex-1 shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-[6px] px-3 text-footnote font-medium text-muted no-underline outline-none transition-colors duration-(--duration-fast) hover:text-fg focus-visible:ring-2 focus-visible:ring-accent/50 data-[state=active]:bg-surface data-[state=active]:text-fg data-[state=active]:shadow-e1 aria-[current=page]:bg-surface aria-[current=page]:text-fg aria-[current=page]:shadow-e1 max-md:px-2";

export function TabsList({ className, ...props }: React.ComponentProps<typeof T.List>) {
  return <T.List className={cn(tabsListClass, className)} {...props} />;
}

export function TabsTrigger({ className, ...props }: React.ComponentProps<typeof T.Trigger>) {
  return <T.Trigger className={cn(tabsTriggerClass, className)} {...props} />;
}
