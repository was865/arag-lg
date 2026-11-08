"use client";

// ThemeToggle：浅色/深色主题切换按钮（chat 顶栏与 agent 顶栏共用）。
// 图标用 Icon sun/moon（描边风格），文案走 i18n（workspace.toLight/toDark/themeToggleAriaLabel）。

import { Icon } from "@/components/icons";
import { useT } from "@/i18n/context";
import { cn } from "@/lib/utils";

export interface ThemeToggleProps {
  /** 当前是否深色模式。 */
  dark: boolean;
  /** 点击切换回调。 */
  onToggle: () => void;
  /** 追加样式（覆盖尺寸/定位时用）。 */
  className?: string;
}

/** 顶栏主题切换按钮（纯展示 + i18n）。 */
export function ThemeToggle({ dark, onToggle, className }: ThemeToggleProps) {
  const { t } = useT();
  return (
    <button
      type="button"
      onClick={onToggle}
      title={dark ? t.workspace.toLight : t.workspace.toDark}
      aria-label={t.workspace.themeToggleAriaLabel}
      className={cn(
        "grid h-[30px] w-[30px] place-items-center rounded-lg border-0 bg-transparent text-muted hover:bg-divider hover:text-fg",
        className,
      )}
    >
      <Icon name={dark ? "sun" : "moon"} size={14} />
    </button>
  );
}
