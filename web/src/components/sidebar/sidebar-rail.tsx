"use client";

// SidebarRail：折叠态 48px 图标栏の外壳（chat 与 agent 共用）。
// 上部に「展开 >」「新建 +」を固定し、その下に页面専属图标を children で差し込む
//（chat=知识库/回收站、agent=能力パッケージ图标リスト）。桌面端折叠时にのみ描画される。

import type { ReactNode } from "react";

import { Icon, type IconName } from "@/components/icons";
import { cn } from "@/lib/utils";

export interface SidebarRailProps {
  /** 展开ボタン回调（折叠解除）。 */
  onExpand: () => void;
  /** 新建ボタン回调。 */
  onNew: () => void;
  /** 展开ボタンの aria-label/title。 */
  expandLabel: string;
  /** 新建ボタンの aria-label/title。 */
  newLabel: string;
  /** 页面専属图标（SidebarRailButton 推奨）。 */
  children?: ReactNode;
}

/** 折叠态 icon rail（桌面 ≥769px）。移动端は抽屉が闭じるため非描画。 */
export function SidebarRail({ onExpand, onNew, expandLabel, newLabel, children }: SidebarRailProps) {
  return (
    <aside className="relative flex flex-col items-center gap-2 overflow-hidden border-r-[0.5px] border-divider bg-bg-2 py-3 max-tablet:hidden">
      <SidebarRailButton icon="chevronRight" label={expandLabel} onClick={onExpand} />
      <SidebarRailButton icon="plus" label={newLabel} onClick={onNew} emphasis />
      {children}
    </aside>
  );
}

export interface SidebarRailButtonProps {
  icon: IconName;
  label: string;
  onClick: () => void;
  /** 选中态（accent 高亮）。 */
  active?: boolean;
  /** 強調表示（rest 時 text-fg）。primary なアクション（新建）用。 */
  emphasis?: boolean;
}

/** rail 内の统一スタイル icon 按钮。 */
export function SidebarRailButton({ icon, label, onClick, active = false, emphasis = false }: SidebarRailButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      data-active={active ? "true" : "false"}
      className={cn(
        "grid h-8 w-8 place-items-center rounded-control border-0 bg-transparent",
        active
          ? "bg-accent-soft text-accent"
          : emphasis
            ? "text-fg hover:bg-divider"
            : "text-muted hover:bg-divider hover:text-fg",
      )}
    >
      <Icon name={icon} size={14} />
    </button>
  );
}
