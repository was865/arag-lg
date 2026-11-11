"use client";

/**
 * グループ化した一覧（iOS / macOS の設定画面の Inset Grouped List）。
 * 設定・アカウント・管理画面の「項目と値」はこれで並べる。
 */
import { cn } from "@/lib/utils";

export function ListGroup({
  title,
  footer,
  children,
  className,
}: {
  title?: React.ReactNode;
  footer?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("flex flex-col gap-1.5", className)}>
      {title && <h3 className="m-0 px-3.5 text-caption font-medium text-muted">{title}</h3>}
      <div className="overflow-hidden rounded-card border-[0.5px] border-divider bg-surface">{children}</div>
      {footer && <p className="m-0 px-3.5 text-caption text-muted">{footer}</p>}
    </section>
  );
}

/** グループ内の 1 行（行の間は細い区切り線） */
export function ListItem({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "flex min-h-[44px] items-center gap-3 px-3.5 py-2 [&+&]:border-t-[0.5px] [&+&]:border-divider",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** 「名前（＋説明）と操作部品」の行 */
export function ListField({
  label,
  hint,
  badge,
  changed,
  children,
}: {
  label: React.ReactNode;
  hint?: React.ReactNode;
  /** 技術者向けの用語（Top-K など） */
  badge?: React.ReactNode;
  /** 既定から変えた印 */
  changed?: boolean;
  children: React.ReactNode;
}) {
  return (
    <ListItem className="max-md:flex-wrap">
      <div className="min-w-0 flex-1 py-0.5">
        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-body text-fg">
          {label}
          {badge && (
            <span className="rounded-[4px] bg-divider px-1.5 font-mono text-[10.5px] text-muted">{badge}</span>
          )}
          {changed && <span aria-label="既定から変更" className="h-1.5 w-1.5 rounded-full bg-accent" />}
        </div>
        {hint && <div className="text-caption text-muted">{hint}</div>}
      </div>
      <div className="flex shrink-0 items-center">{children}</div>
    </ListItem>
  );
}
