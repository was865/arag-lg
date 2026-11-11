"use client";

/** 1 行の入力欄と、その見出し（UI 試作）。 */
import { cn } from "@/lib/utils";

export const inputClass =
  "h-9 w-full rounded-control border-[0.5px] border-divider-strong bg-surface px-3 text-body text-fg outline-none transition-[border-color,box-shadow] placeholder:text-muted-2 focus:border-accent focus:ring-2 focus:ring-accent/20 disabled:opacity-50";

export function Input({ className, ...props }: React.ComponentProps<"input">) {
  return <input className={cn(inputClass, className)} {...props} />;
}

/** 見出し付きの入力欄（label で包むのでクリックで入力欄に移る） */
export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: React.ReactNode;
  hint?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("grid gap-1.5", className)}>
      <span className="text-footnote font-medium text-fg-2">{label}</span>
      {children}
      {hint && <span className="text-caption text-muted">{hint}</span>}
    </label>
  );
}
