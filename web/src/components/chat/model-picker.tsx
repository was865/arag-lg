"use client";

// ModelPicker：Composer の「モデル」ボタンに錨定するモデル選択ポップオーバー。
// 設定モーダルを開かずその場で切替できる軽量経路として、chat / agents の双方から使う。

import { OptionBadge, Popover, PopoverContent, PopoverOption, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import type { ModelOption } from "@/lib/types";
import { useT } from "@/i18n/context";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 錨定先（Composer のモデルボタン）。ポップオーバーはこの上に右揃えで出す */
  children: React.ReactNode;
  models: ModelOption[];
  /** 現在選択中のモデル id。 */
  value: string;
  onChange: (model: ModelOption) => void;
}

export function ModelPicker({ open, onOpenChange, children, models, value, onChange }: Props) {
  const { t } = useT();

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent side="top" align="end" title={t.modals.navModel} className="w-[280px]">
        <div className="overflow-y-auto p-1.5">
          {models.map((m) => {
            const active = m.id === value;
            // API キー未設定のモデルは選択不可（理由はツールチップと「未設定」バッジで示す）。
            const unavailable = m.available === false;
            return (
              <PopoverOption
                key={m.id}
                disabled={unavailable}
                title={unavailable ? t.modals.modelUnavailableHint : undefined}
                selected={active}
                icon={<span className={cn("h-1.5 w-1.5 rounded-full", active ? "bg-accent" : "bg-divider-strong")} />}
                label={m.label}
                badge={
                  <>
                    {m.tag && <OptionBadge tone="accent">{m.tag}</OptionBadge>}
                    {unavailable && <OptionBadge>{t.modals.modelUnavailable}</OptionBadge>}
                  </>
                }
                hint={m.desc}
                onClick={() => {
                  onChange(m);
                  onOpenChange(false);
                }}
              />
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
