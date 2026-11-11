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
        // 墨色の主ボタン（specs/025 R40）。kbd は地に溶かす
        "mx-3 mb-2 flex h-9 items-center gap-2 rounded-card border-0 bg-fg px-3 text-body font-semibold text-bg shadow-e1 transition-[opacity,transform] duration-(--duration-fast) hover:opacity-90 active:scale-[0.98] [&>kbd]:border-0 [&>kbd]:bg-transparent [&>kbd]:text-bg/60",
        className,
      )}
    >
      <Icon name={icon} size={13} />
      <span className="flex-1 text-left">{label}</span>
      {shortcut && <kbd>{shortcut}</kbd>}
    </button>
  );
}
