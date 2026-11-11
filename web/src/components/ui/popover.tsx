"use client";

/**
 * ポップオーバー（UI 試作）。ボタンに錨定した小さな面（選択リスト・短い入力）。
 * 位置合わせ・外側クリック・Esc・フォーカス復帰は Radix Popover が受け持つ。
 * 項目を選ぶだけなら Menu、入力や切り替えを含むならこちらを使う。
 */
import * as P from "@radix-ui/react-popover";
import { floatingSurface } from "@/components/ui/menu";
import { cn } from "@/lib/utils";

export const Popover = P.Root;
export const PopoverTrigger = P.Trigger;
export const PopoverAnchor = P.Anchor;
export const PopoverClose = P.Close;

export function PopoverContent({
  title,
  className,
  children,
  sideOffset = 6,
  collisionPadding = 10,
  ...props
}: Omit<React.ComponentProps<typeof P.Content>, "title"> & {
  /** 上部の見出し（区切り線つき） */
  title?: React.ReactNode;
}) {
  return (
    <P.Portal>
      <P.Content
        sideOffset={sideOffset}
        collisionPadding={collisionPadding}
        className={cn(
          floatingSurface,
          "flex max-h-[min(480px,var(--radix-popover-content-available-height))] max-w-[calc(100vw-20px)] origin-(--radix-popover-content-transform-origin) flex-col overflow-hidden",
          className,
        )}
        {...props}
      >
        {title && (
          <div className="shrink-0 border-b-[0.5px] border-divider px-3.5 py-2.5 text-footnote font-semibold text-muted">
            {title}
          </div>
        )}
        {children}
      </P.Content>
    </P.Portal>
  );
}

/** ポップオーバー内の選択行（1 つだけ選ぶリスト）。選ばれた行は淡い強調とチェック */
export function PopoverOption({
  selected,
  icon,
  label,
  badge,
  hint,
  className,
  ...props
}: Omit<React.ComponentProps<"button">, "children"> & {
  selected?: boolean;
  icon?: React.ReactNode;
  label: React.ReactNode;
  badge?: React.ReactNode;
  hint?: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      className={cn(
        "flex w-full items-center gap-2.5 rounded-control px-2.5 py-2 text-left outline-none transition-colors",
        "focus-visible:bg-divider disabled:cursor-not-allowed disabled:opacity-50",
        selected ? "bg-accent-soft" : "enabled:hover:bg-divider",
        className,
      )}
      {...props}
    >
      {icon && (
        <span className={cn("inline-flex w-4 shrink-0 items-center justify-center", selected ? "text-accent" : "text-muted")}>
          {icon}
        </span>
      )}
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          <span className="truncate text-body font-semibold text-fg">{label}</span>
          {badge}
        </span>
        {hint && <span className="mt-px block truncate text-caption text-muted">{hint}</span>}
      </span>
      {selected && (
        <svg viewBox="0 0 16 16" width="12" height="12" className="shrink-0 text-accent" aria-hidden>
          <path d="M3 8l3.5 3.5L13 5" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </button>
  );
}
