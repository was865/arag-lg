"use client";

/** 管理画面の共通ヘッダ（チャットへ戻る・メンバー・部門・ナレッジベース・監査ログ・フィードバック・利用状況・モデル）。 */
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { Icon } from "@/components/icons";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "members", href: "/admin/members", label: "メンバー" },
  { key: "departments", href: "/admin/departments", label: "部門" },
  { key: "kbs", href: "/admin/kbs", label: "ナレッジベース" },
  { key: "audit", href: "/admin/audit", label: "監査ログ" },
  { key: "feedback", href: "/admin/feedback", label: "フィードバック" },
  { key: "analytics", href: "/admin/analytics", label: "利用状況" },
  { key: "models", href: "/admin/models", label: "モデル" },
] as const;

/** 未対応の「良くない」の報告の件数（ナビに小さく出す。specs/028 R13）。取れなければ出さない。 */
function useOpenFeedback(): number {
  const [n, setN] = useState(0);
  useEffect(() => {
    let alive = true;
    fetch("/api/v1/admin/feedback?limit=1", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((b: { open_count?: number } | null) => {
        if (alive && b?.open_count) setN(b.open_count);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);
  return n;
}

export function AdminHeader({
  current,
  children,
  openFeedback: given,
}: {
  current: (typeof TABS)[number]["key"];
  children?: ReactNode;
  /** フィードバックの画面が自分で数えた件数（状態を変えたらすぐ合わせる）。無ければ自分で取る */
  openFeedback?: number;
}) {
  const fetched = useOpenFeedback();
  const openFeedback = given ?? fetched;
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
              {t.key === "feedback" && openFeedback > 0 && (
                <span className="nums ml-1 rounded-full bg-danger-soft px-1.5 text-mini font-semibold text-danger">{openFeedback}</span>
              )}
            </Link>
          ))}
        </nav>
      </div>
      {children}
    </header>
  );
}
