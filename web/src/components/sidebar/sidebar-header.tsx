"use client";

// SidebarHeader：侧栏顶部栏（chat 与 agent 共用）。
// 右側の折叠/关闭按钮は桌面=折叠・移动=抽屉关闭を兼ねる（chevronLeft）。

import { BrandMark } from "@/components/icons";
import { IconButton } from "@/components/ui/button";

export interface SidebarHeaderProps {
  /** 折叠/关闭按钮の回调（桌面=折叠・移动=抽屉关闭）。 */
  onToggle: () => void;
  /** 折叠/关闭按钮の aria-label/title。 */
  closeLabel: string;
}

/** サイドバー上部: ブランド + 折りたたみ/閉じるボタン。 */
export function SidebarHeader({ onToggle, closeLabel }: SidebarHeaderProps) {
  return (
    <div className="flex items-center justify-between py-3 pl-[14px] pr-3 pb-2">
      <div className="flex items-center gap-2 text-[14px] font-bold tracking-[-0.01em]">
          <div className="grid h-[22px] w-[22px] place-items-center rounded-md bg-accent text-white">
            <BrandMark size={14} />
          </div>
          <span>ARag</span>
        </div>
      <IconButton
        onClick={onToggle}
        label={closeLabel}
        icon="chevronLeft"
        iconSize={13}
      />
    </div>
  );
}
