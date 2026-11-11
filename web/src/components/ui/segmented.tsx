"use client";

/** セグメント（排他的な選択肢 2〜4 個。macOS / iOS の Segmented Control）。 */
import { cn } from "@/lib/utils";

export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  size = "sm",
  className,
}: {
  label: string;
  value: T;
  /** 表示は文字だけでなく件数などを添えてもよい */
  options: readonly (readonly [T, React.ReactNode])[];
  onChange: (v: T) => void;
  /** sm は設定の行の中、md はツールバー */
  size?: "sm" | "md";
  className?: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cn("inline-flex rounded-control bg-divider p-0.5", className)}>
      {options.map(([v, l]) => (
        <button
          key={v}
          type="button"
          role="radio"
          aria-checked={value === v}
          onClick={() => onChange(v)}
          className={cn(
            "inline-flex flex-1 items-center justify-center gap-1 whitespace-nowrap rounded-[6px] px-2.5 text-footnote font-medium transition-colors",
            size === "md" ? "h-7" : "h-6",
            value === v ? "bg-surface text-fg shadow-e1" : "text-muted hover:text-fg",
          )}
        >
          {l}
        </button>
      ))}
    </div>
  );
}
