"use client";

/** iOS 風のオン・オフ切り替え（Radix Switch。キーボード・スクリーンリーダーの扱いは Radix に任せる）。 */
import * as S from "@radix-ui/react-switch";
import { cn } from "@/lib/utils";

export function Switch({
  label,
  checked,
  onChange,
  disabled,
  size = "md",
  className,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  /** sm はポップオーバーなど狭い場所の行の中で使う */
  size?: "sm" | "md";
  className?: string;
}) {
  return (
    <S.Root
      aria-label={label}
      checked={checked}
      onCheckedChange={onChange}
      disabled={disabled}
      className={cn(
        "relative inline-flex shrink-0 cursor-pointer rounded-full bg-divider-strong transition-colors outline-none focus-visible:ring-2 focus-visible:ring-accent/50 disabled:opacity-45 data-[state=checked]:bg-accent",
        size === "sm" ? "h-4 w-7" : "h-[22px] w-[38px]",
        className,
      )}
    >
      <S.Thumb
        className={cn(
          "absolute rounded-full bg-white shadow-e1 transition-transform",
          size === "sm"
            ? "left-0.5 top-0.5 h-3 w-3 data-[state=checked]:translate-x-3"
            : "left-[3px] top-[3px] h-4 w-4 data-[state=checked]:translate-x-4",
        )}
      />
    </S.Root>
  );
}
