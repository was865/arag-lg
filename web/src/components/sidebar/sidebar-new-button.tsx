"use client";

// SidebarNewButton：侧栏「新建」按钮（chat 与 agent 共用）。
// 纯展示・受控。shortcut を渡すと末尾に ⌘ 徽标を出す（chat の ⌘N 同款）。

import { Icon, type IconName } from "@/components/icons";
import { cn } from "@/lib/utils";

export interface SidebarNewButtonProps {
  /** 按钮文案（chat=新对话 / agent=新建测算）。 */
  label: string;
  /** クリック回调。 */
  onClick: () => void;
  /** 渡すと末尾に kbd 徽标を出す（例 "⌘N"）。未指定なら出さない。 */
  shortcut?: string;
  /** 先头图标（既定 plus）。 */
  icon?: IconName;
  /** 追加 class（マージン上書き等）。 */
  className?: string;
}

/** 侧栏「新建」按钮：+ 图标 + 文案 + 可选 ⌘ 徽标。 */
export function SidebarNewButton({ label, onClick, shortcut, icon = "plus", className }: SidebarNewButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "mx-3 mb-2 flex h-9 items-center gap-2 rounded-card border border-divider-strong bg-surface px-3 text-body font-medium text-fg shadow-e1 hover:bg-surface-2",
        className,
      )}
    >
      <Icon name={icon} size={13} />
      <span className="flex-1 text-left">{label}</span>
      {shortcut && <kbd>{shortcut}</kbd>}
    </button>
  );
}
