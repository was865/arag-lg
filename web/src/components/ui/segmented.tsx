"use client";

/**
 * セグメント（排他的な選択肢 2〜4 個。macOS / iOS の Segmented Control）。
 * 選択中の白い背景は、選び直すと新しい選択肢へ滑って移る（specs/025 R12。Motion の layoutId）。
 */
import { useId } from "react";
import { m } from "motion/react";
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
  // 同じ画面に複数あっても背景が別の部品へ飛ばないよう、部品ごとに名前を分ける
  const thumbId = `segmented-thumb-${useId()}`;
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
            "relative inline-flex flex-1 items-center justify-center gap-1 whitespace-nowrap rounded-[6px] px-2.5 text-footnote font-medium transition-colors",
            size === "md" ? "h-7" : "h-6",
            value === v ? "text-fg" : "text-muted hover:text-fg",
          )}
        >
          {value === v && (
            <m.span
              data-segmented-thumb
              layoutId={thumbId}
              aria-hidden
              className="absolute inset-0 rounded-[6px] bg-surface shadow-e1"
            />
          )}
          <span className="relative inline-flex items-center gap-1">{l}</span>
        </button>
      ))}
    </div>
  );
}
