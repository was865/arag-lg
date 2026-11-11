"use client";

// AppShell：知识助手（chat）与业务智能体（agent）共用的外壳框架（纯布局，无业务状态）。
// 拥有：响应式 grid 根（sidebar | main | 可选 rightPanel）+ 移动/平板抽屉遮罩（backdrop）。
// 不拥有：折叠/右面板/媒体查询等状态——全部由容器层受控传入，保证迁移行为零变化。
// 模态等 fixed 浮层不放进 AppShell，由容器层作为 AppShell 的兄弟节点渲染（fixed 定位与 DOM 位置无关）。

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface AppShellProps {
  /** 左侧栏插槽（chat 的 Sidebar / agent 的 AgentSidebar）。移动端由各自侧栏内部的抽屉 class 负责。 */
  sidebar: ReactNode;
  /** 主列插槽（header + body + composer）。 */
  children: ReactNode;
  /** 右侧面板插槽（chat=引用面板 / agent=知识库面板）。仅在 rightPanelShown 时由容器层传入元素。 */
  rightPanel?: ReactNode;
  /** 侧栏是否折叠（驱动 data-sb 与 grid 列宽 260↔48）。 */
  sidebarCollapsed: boolean;
  /** 右面板是否展示（驱动 data-rp 与第三列）。 */
  rightPanelShown: boolean;
  /** 右面板宽度（写入 --rp-width）。 */
  panelWidth: number;
  /** 紧凑密度（整体字号 13px）。 */
  compact: boolean;
  /** 抽屉遮罩是否可见（移动/平板）。 */
  backdropVisible: boolean;
  /** 点击遮罩触发（容器层据此关闭侧栏抽屉 / 右面板）。 */
  onBackdropClick: () => void;
}

/**
 * 外壳框架（纯展示）。grid 列模板与 chat 历史实现逐字一致，迁移须保行为：
 *   - 移动端：单列（侧栏/右面板为 fixed 覆盖层，由各自组件内部负责）
 *   - tablet/wide：[侧栏 260/48 | 主列 1fr]，wide 且右面板开时追加第三列 var(--rp-width)
 */
export function AppShell({
  sidebar,
  children,
  rightPanel,
  sidebarCollapsed,
  rightPanelShown,
  panelWidth,
  compact,
  backdropVisible,
  onBackdropClick,
}: AppShellProps) {
  return (
    <div
      className={cn(
        // 左上の淡い朱の光は、半透明のサイドバー越しに見える（specs/025 R44）
        "group/shell grid h-dvh overflow-hidden bg-bg bg-[radial-gradient(520px_320px_at_0%_0%,var(--accent-soft),transparent_70%)] text-callout",
        compact && "text-body",
        "grid-cols-[1fr]",
        "tablet:grid-cols-[260px_minmax(0,1fr)] tablet:data-[sb=collapsed]:grid-cols-[48px_minmax(0,1fr)]",
        "wide:grid-cols-[260px_minmax(0,1fr)] wide:data-[sb=collapsed]:grid-cols-[48px_minmax(0,1fr)]",
        "wide:data-[rp=open]:grid-cols-[260px_minmax(0,1fr)_var(--rp-width)] wide:data-[sb=collapsed]:data-[rp=open]:grid-cols-[48px_minmax(0,1fr)_var(--rp-width)]",
      )}
      data-sb={sidebarCollapsed ? "collapsed" : "open"}
      data-rp={rightPanelShown ? "open" : "closed"}
      style={{ ["--rp-width" as string]: `${panelWidth}px` }}
    >
      {sidebar}

      {children}

      {rightPanel}

      {/* Drawer backdrop (mobile + tablet) */}
      <div
        className="hidden fixed inset-0 z-[55] bg-[rgba(15,13,10,0.42)] opacity-0 backdrop-blur-[2px] transition-opacity duration-150 [pointer-events:none] data-[visible=true]:opacity-100 data-[visible=true]:[pointer-events:auto] max-wide:block"
        data-visible={backdropVisible ? "true" : "false"}
        onClick={onBackdropClick}
        aria-hidden
      />
    </div>
  );
}
