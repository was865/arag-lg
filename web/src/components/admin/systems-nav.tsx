"use client";

/** 社内システムの管理の「システム / ツール」の切り替え（URL で分かれるのでタブの見た目のリンク。specs/038 R13）。 */
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { tabsListClass, tabsTriggerClass } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

export function SystemsNav({ current, pending = 0 }: { current: "servers" | "tools"; pending?: number }) {
  const tabs = [
    { key: "servers", href: "/admin/systems", label: "システム" },
    { key: "tools", href: "/admin/systems/tools", label: "ツール" },
  ] as const;
  return (
    <nav aria-label="社内システムの区分" className={cn(tabsListClass, "self-start")}>
      {tabs.map((t) => (
        <Link
          key={t.key}
          href={t.href}
          aria-current={current === t.key ? "page" : undefined}
          className={tabsTriggerClass}
        >
          {t.label}
          {t.key === "tools" && pending > 0 && (
            <Badge tone="danger" title={`審査待ち ${pending} 件`}>
              {pending}
            </Badge>
          )}
        </Link>
      ))}
    </nav>
  );
}
