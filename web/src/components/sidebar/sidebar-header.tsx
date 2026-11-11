"use client";

// SidebarHeader：侧栏顶部栏（chat 与 agent 共用）。
// 右側の折叠/关闭按钮は桌面=折叠・移动=抽屉关闭を兼ねる（chevronLeft）。

import { Seal } from "@/components/ui/seal";
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
      {/* ブランド: 明朝の「ARag」と、右上の引用の印（specs/025 R43） */}
      <div className="flex items-start gap-0.5 font-display text-title font-bold leading-none tracking-[0.01em]">
        <span>ARag</span>
        <Seal className="mt-px h-2 min-w-2 rounded-[2px] px-0" />
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
