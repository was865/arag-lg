"use client";

/** 管理画面の共通ヘッダ（チャットへ戻る・メンバー・監査ログ）。 */
import Link from "next/link";
import type { ReactNode } from "react";
import { Icon } from "@/components/icons";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "members", href: "/admin/members", label: "メンバー" },
  { key: "audit", href: "/admin/audit", label: "監査ログ" },
] as const;

export function AdminHeader({ current, children }: { current: (typeof TABS)[number]["key"]; children?: ReactNode }) {
  return (
    <header className="flex h-[52px] items-center gap-2 border-b-[0.5px] border-divider px-[18px] max-md:px-2.5">
      <Link
        href="/"
        aria-label="チャットへ戻る"
        className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-lg text-fg no-underline hover:bg-divider"
      >
        <Icon name="chevronLeft" size={16} />
      </Link>
      <nav aria-label="管理" className="flex min-w-0 flex-1 items-center gap-1">
        {TABS.map((t) => (
          <Link
            key={t.key}
            href={t.href}
            aria-current={current === t.key ? "page" : undefined}
            className={cn(
              "rounded-md px-2.5 py-1 text-[13.5px] no-underline",
              current === t.key ? "bg-surface-2 font-semibold text-fg" : "font-medium text-muted hover:text-fg",
            )}
          >
            {t.label}
          </Link>
        ))}
      </nav>
      {children}
    </header>
  );
}
