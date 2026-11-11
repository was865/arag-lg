"use client";

/** 管理画面の共通ヘッダ（チャットへ戻る・メンバー・部門・ナレッジベース・監査ログ・利用状況・モデル）。 */
import Link from "next/link";
import type { ReactNode } from "react";
import { Icon } from "@/components/icons";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "members", href: "/admin/members", label: "メンバー" },
  { key: "departments", href: "/admin/departments", label: "部門" },
  { key: "kbs", href: "/admin/kbs", label: "ナレッジベース" },
  { key: "audit", href: "/admin/audit", label: "監査ログ" },
  { key: "analytics", href: "/admin/analytics", label: "利用状況" },
  { key: "models", href: "/admin/models", label: "モデル" },
] as const;

export function AdminHeader({ current, children }: { current: (typeof TABS)[number]["key"]; children?: ReactNode }) {
  return (
    <header className="flex h-[52px] items-center gap-2 border-b-[0.5px] border-divider px-[18px] max-md:px-2.5">
      <Link
        href="/"
        aria-label="チャットへ戻る"
        className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-control text-fg no-underline hover:bg-divider"
      >
        <Icon name="chevronLeft" size={16} />
      </Link>
      {/* 区分の切り替えはセグメントと同じ見た目にする（今いる場所が白い面で浮く。specs/025 R47） */}
      <div className="flex min-w-0 flex-1 items-center overflow-x-auto [scrollbar-width:none]">
        <nav aria-label="管理" className="flex shrink-0 items-center rounded-control bg-divider p-0.5">
          {TABS.map((t) => (
            <Link
              key={t.key}
              href={t.href}
              aria-current={current === t.key ? "page" : undefined}
              className={cn(
                "shrink-0 whitespace-nowrap rounded-[6px] px-3 py-1 text-footnote font-medium no-underline transition-colors duration-(--duration-fast) max-md:px-2",
                current === t.key ? "bg-surface text-fg shadow-e1" : "text-muted hover:text-fg",
              )}
            >
              {t.label}
            </Link>
          ))}
        </nav>
      </div>
      {children}
    </header>
  );
}
