"use client";

// ThemeToggle：浅色/深色主题切换按钮（chat 顶栏与 agent 顶栏共用）。
// 图标用 Icon sun/moon（描边风格），文案走 i18n（workspace.toLight/toDark/themeToggleAriaLabel）。

import { IconButton } from "@/components/ui/button";
import { useT } from "@/i18n/context";

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
    <IconButton
      label={t.workspace.themeToggleAriaLabel}
      tooltip={false}
      title={dark ? t.workspace.toLight : t.workspace.toDark}
      icon={dark ? "sun" : "moon"}
      onClick={onToggle}
      className={className}
    />
  );
}
