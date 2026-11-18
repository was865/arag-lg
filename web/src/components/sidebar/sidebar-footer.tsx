"use client";

// SidebarUserFooter：侧栏底部用户身份栏 + 弹出用户菜单（chat 与 agent 共用）。
// 纯展示层：用户头像/名字/组织 + 点击弹出浮层菜单（邮箱 / 管理控制台 / 设置 / 主题 / 帮助 / 退出）。
// 回调可选——未传入的菜单项不渲染（agent 精简版只用 主题切换 / 退出，+ 有权限时管理控制台）。

import { Icon } from "@/components/icons";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
import { useT } from "@/i18n/context";
import { SHORTCUT_LABEL } from "@/lib/shortcuts";
import type { AppUser } from "@/lib/types";

export interface SidebarUserFooterProps {
  /** 当前登录用户（头像缩写 / 名字 / 组织 / 邮箱）。 */
  user: AppUser;
  /** 当前是否深色模式（主题项图标/文案）。 */
  dark: boolean;
  /** 主题切换回调。 */
  onToggleTheme: () => void;
  /** 退出登录回调。 */
  onSignOut?: () => void;
  /** 打开设置；未传则不渲染设置项（agent 当前无设置弹窗）。 */
  onOpenSettings?: () => void;
  /** 打开管理控制台；仅 org admin / 部门管理者传入。 */
  onOpenAdmin?: () => void;
  /** 打开只读工作日历；未传则不渲染该项。 */
  onOpenWorkCalendar?: () => void;
  /** 打开帮助；未传则不渲染帮助项（agent 当前无帮助面板）。 */
  onOpenHelp?: () => void;
}

/** 侧栏底部用户栏：头像 + 名字 + 组织，点击弹出用户菜单（共通 Menu）。 */
export function SidebarUserFooter({
  user,
  dark,
  onToggleTheme,
  onSignOut,
  onOpenSettings,
  onOpenAdmin,
  onOpenWorkCalendar,
  onOpenHelp,
}: SidebarUserFooterProps) {
  const { t } = useT();

  return (
    <div className="border-t-[0.5px] border-divider p-2">
      <Menu>
        <MenuTrigger asChild>
          <button
            data-tour="user-menu"
            className="flex w-full items-center gap-2.5 rounded-control bg-transparent px-2 py-1.5 outline-none hover:bg-divider focus-visible:ring-2 focus-visible:ring-accent/50 data-[state=open]:bg-divider"
          >
            <div className="grid h-[30px] w-[30px] place-items-center rounded-full bg-accent-fill text-caption font-semibold tracking-[0.02em] text-white">
              {user.initials}
            </div>
            <div className="min-w-0 flex-1 text-left">
              <div className="truncate text-footnote font-semibold text-fg">{user.name}</div>
              <div className="truncate text-mini text-muted">{user.org}</div>
            </div>
            <svg viewBox="0 0 16 16" width="12" height="12" className="text-muted-2" aria-hidden>
              <path d="M3 6l3 3 3-3M3 10l3 3 3-3" transform="translate(2 -2)" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </MenuTrigger>
        {/* 上に開き、幅はトリガーに合わせる（220〜280px） */}
        <MenuContent
          side="top"
          align="start"
          className="w-[clamp(220px,calc(var(--radix-dropdown-menu-trigger-width)+16px),280px)] p-1.5"
        >
          <MenuLabel className="px-3 font-mono tracking-[-0.005em]" title={user.email}>
            {user.email}
          </MenuLabel>
          {/* 管理コンソールへの導線（org admin / 部門管理者のみ）。チャットから離れる
              「目的地」なので、通常の操作項目より一段格上げしてカード状に見せる。 */}
          {onOpenAdmin && (
            <>
              <MenuItem
                onSelect={onOpenAdmin}
                className="mb-1 gap-2.5 rounded-control border-[0.5px] border-divider bg-accent-soft px-2 py-2 data-[highlighted]:border-divider-strong data-[highlighted]:bg-accent-soft"
              >
                <span className="flex items-center gap-2.5">
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-control bg-accent-fill text-white">
                    <Icon name="building" size={14} />
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate text-footnote font-semibold leading-tight text-fg">{t.sidebar.adminConsole}</span>
                    <span className="truncate text-mini leading-tight text-muted">{t.sidebar.adminConsoleHint}</span>
                  </span>
                  <Icon
                    name="chevronRight"
                    size={14}
                    className="shrink-0 text-muted-2 transition-transform group-data-[highlighted]/mi:translate-x-0.5"
                  />
                </span>
              </MenuItem>
              <MenuSeparator className="mx-0" />
            </>
          )}
          {onOpenSettings && (
            <MenuItem icon="cog" shortcut={SHORTCUT_LABEL.settings} onSelect={onOpenSettings}>
              {t.sidebar.settings}
            </MenuItem>
          )}
          {/* テーマ切り替えはメニューを開いたまま結果を見せる */}
          <MenuItem
            icon={dark ? "sun" : "moon"}
            onSelect={(e) => {
              e.preventDefault();
              onToggleTheme();
            }}
          >
            {dark ? t.sidebar.lightMode : t.sidebar.darkMode}
          </MenuItem>
          {onOpenWorkCalendar && (
            <MenuItem icon="calendar" onSelect={onOpenWorkCalendar}>
              {t.sidebar.workCalendar}
            </MenuItem>
          )}
          {onOpenHelp && (
            <MenuItem
              icon={
                <svg viewBox="0 0 16 16" width="14" height="14" fill="none" aria-hidden>
                  <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.4" />
                  <path d="M6 6.5a2 2 0 014 0c0 .8-.5 1.2-1 1.5s-1 .5-1 1.2M8 11.4v.1" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                </svg>
              }
              shortcut="?"
              onSelect={onOpenHelp}
            >
              {t.sidebar.showHelp}
            </MenuItem>
          )}
          {onSignOut && (
            <>
              <MenuSeparator />
              <MenuItem icon="signout" onSelect={onSignOut}>
                {t.sidebar.signOut}
              </MenuItem>
            </>
          )}
        </MenuContent>
      </Menu>
    </div>
  );
}
