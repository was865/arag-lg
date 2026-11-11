"use client";

/** iOS 風のオン・オフ切り替え（Radix Switch。キーボード・スクリーンリーダーの扱いは Radix に任せる）。 */
import * as S from "@radix-ui/react-switch";
import { cn } from "@/lib/utils";

export function Switch({
  label,
  checked,
  onChange,
  disabled,
  className,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <S.Root
      aria-label={label}
      checked={checked}
      onCheckedChange={onChange}
      disabled={disabled}
      className={cn(
        "relative inline-flex h-[22px] w-[38px] shrink-0 cursor-pointer rounded-full bg-divider-strong transition-colors outline-none focus-visible:ring-2 focus-visible:ring-accent/50 disabled:opacity-45 data-[state=checked]:bg-accent",
        className,
      )}
    >
      <S.Thumb className="absolute left-[3px] top-[3px] h-4 w-4 rounded-full bg-white shadow-e1 transition-transform data-[state=checked]:translate-x-4" />
    </S.Root>
  );
}
