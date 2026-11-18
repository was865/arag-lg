"use client";

/** 説明つきの選択肢（公開範囲など、選ぶと何が起きるかを 1 行添えたいとき）。 */
import { Icon, type IconName } from "@/components/icons";
import { ICON } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function ChoiceList<T extends string | null>({
  label,
  value,
  options,
  onChange,
  disabled,
}: {
  label: string;
  value: T;
  options: { id: T; label: React.ReactNode; hint?: React.ReactNode; icon?: IconName }[];
  onChange: (v: T) => void;
  disabled?: boolean;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="overflow-hidden rounded-card border-[0.5px] border-divider bg-surface">
      {options.map((o) => {
        const on = o.id === value;
        return (
          <button
            key={o.id ?? "__null"}
            type="button"
            role="radio"
            aria-checked={on}
            disabled={disabled}
            onClick={() => onChange(o.id)}
            className="flex w-full items-center gap-3 px-3.5 py-2.5 text-left transition-colors hover:bg-surface-2 disabled:cursor-wait [&+&]:border-t-[0.5px] [&+&]:border-divider"
          >
            {o.icon && (
              <span
                className={cn(
                  "grid h-7 w-7 shrink-0 place-items-center rounded-control",
                  on ? "bg-accent-fill text-white" : "bg-surface-2 text-muted",
                )}
              >
                <Icon name={o.icon} size={ICON.md} />
              </span>
            )}
            <span className="min-w-0 flex-1">
              <span className="block text-body text-fg">{o.label}</span>
              {o.hint && <span className="block text-caption text-muted">{o.hint}</span>}
            </span>
            <span className={cn("shrink-0 text-accent", !on && "invisible")}>
              <Icon name="check" size={ICON.md} />
            </span>
          </button>
        );
      })}
    </div>
  );
}
