"use client";

/** タブ（Radix Tabs）。見た目はセグメントと同じにして、画面上部の切り替えに使う。 */
import * as T from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";

export const Tabs = T.Root;
export const TabsContent = T.Content;

export function TabsList({ className, ...props }: React.ComponentProps<typeof T.List>) {
  return <T.List className={cn("inline-flex rounded-control bg-divider p-0.5", className)} {...props} />;
}

export function TabsTrigger({ className, ...props }: React.ComponentProps<typeof T.Trigger>) {
  return (
    <T.Trigger
      className={cn(
        "inline-flex h-7 flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-[6px] px-3 text-footnote font-medium text-muted outline-none transition-colors hover:text-fg focus-visible:ring-2 focus-visible:ring-accent/50 data-[state=active]:bg-surface data-[state=active]:text-fg data-[state=active]:shadow-e1",
        className,
      )}
      {...props}
    />
  );
}
