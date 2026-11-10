"use client";

import { cn } from "@/lib/utils";

/** iOS 風のオン・オフ切り替え（設定画面で共用）。 */
export function Switch({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-[22px] w-[38px] rounded-full transition-colors",
        checked ? "bg-accent" : "bg-divider-strong",
      )}
    >
      <span
        className={cn(
          "absolute top-[3px] h-4 w-4 rounded-full bg-white shadow-e1 transition-[left]",
          checked ? "left-[19px]" : "left-[3px]",
        )}
      />
    </button>
  );
}
