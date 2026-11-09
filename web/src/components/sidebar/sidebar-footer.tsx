"use client";

// SidebarUserFooter：侧栏底部用户身份栏 + 弹出用户菜单（chat 与 agent 共用）。
// 纯展示层：用户头像/名字/组织 + 点击弹出浮层菜单（邮箱 / 管理控制台 / 设置 / 主题 / 帮助 / 退出）。
// 回调可选——未传入的菜单项不渲染（agent 精简版只用 主题切换 / 退出，+ 有权限时管理控制台）。

import { useEffect, useRef, useState } from "react";

import { Icon } from "@/components/icons";
import { useT } from "@/i18n/context";
import { SHORTCUT_LABEL } from "@/lib/shortcuts";
import type { AppUser } from "@/lib/types";
import { cn } from "@/lib/utils";

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

/** 侧栏底部用户栏：头像 + 名字 + 组织，点击弹出 UserMenu。 */
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
  const [menuOpen, setMenuOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);

  return (
    <div className="border-t-[0.5px] border-divider p-2">
      <button
        ref={btnRef}
        data-tour="user-menu"
        className={cn(
          "flex w-full items-center gap-2.5 rounded-lg bg-transparent px-2 py-1.5 hover:bg-divider",
          menuOpen && "bg-divider",
        )}
        onClick={() => setMenuOpen((o) => !o)}
      >
        <div className="grid h-[30px] w-[30px] place-items-center rounded-full bg-accent text-[11px] font-semibold tracking-[0.02em] text-white">
          {user.initials}
        </div>
        <div className="min-w-0 flex-1 text-left">
          <div className="truncate text-[12.5px] font-semibold text-fg">{user.name}</div>
          <div className="truncate text-[10.5px] text-muted">{user.org}</div>
        </div>
        <svg viewBox="0 0 16 16" width="12" height="12" className="text-muted-2">
          <path d="M3 6l3 3 3-3M3 10l3 3 3-3" transform="translate(2 -2)" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      <UserMenu
        open={menuOpen}
        anchorRef={btnRef}
        onClose={() => setMenuOpen(false)}
        user={user}
        dark={dark}
        onOpenSettings={onOpenSettings ? () => { setMenuOpen(false); onOpenSettings(); } : undefined}
        onOpenAdmin={onOpenAdmin ? () => { setMenuOpen(false); onOpenAdmin(); } : undefined}
        onOpenWorkCalendar={onOpenWorkCalendar ? () => { setMenuOpen(false); onOpenWorkCalendar(); } : undefined}
        onOpenHelp={onOpenHelp ? () => { setMenuOpen(false); onOpenHelp(); } : undefined}
        onToggleTheme={onToggleTheme}
        onSignOut={onSignOut ? () => { setMenuOpen(false); onSignOut(); } : undefined}
      />
    </div>
  );
}

interface UserMenuProps {
  open: boolean;
  anchorRef: React.RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  user: AppUser;
  dark: boolean;
  onOpenSettings?: () => void;
  onOpenAdmin?: () => void;
  onOpenWorkCalendar?: () => void;
  onOpenHelp?: () => void;
  onToggleTheme: () => void;
  onSignOut?: () => void;
}

function UserMenu({ open, anchorRef, onClose, user, dark, onOpenSettings, onOpenAdmin, onOpenWorkCalendar, onOpenHelp, onToggleTheme, onSignOut }: UserMenuProps) {
  const { t } = useT();
  const menuRef = useRef<HTMLDivElement>(null);
  const [style, setStyle] = useState<React.CSSProperties>({});

  // Position above the anchor button (fixed coords escape the sidebar's clip).
  useEffect(() => {
    if (!open || !anchorRef.current) return;
    const rect = anchorRef.current.getBoundingClientRect();
    setStyle({
      left: Math.max(8, rect.left),
      bottom: window.innerHeight - rect.top + 6,
      width: Math.max(220, Math.min(280, rect.width + 16)),
    });
  }, [open, anchorRef]);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (menuRef.current?.contains(e.target as Node)) return;
      if (anchorRef.current?.contains(e.target as Node)) return;
      onClose();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose, anchorRef]);

  if (!open) return null;

  const itemCls =
    "group/mi flex w-full items-center gap-3 rounded-[7px] border-0 bg-transparent px-2.5 py-2 text-left text-[13px] text-fg transition-colors hover:bg-divider";
  const iconCls = "inline-flex w-[18px] shrink-0 items-center justify-center text-muted group-hover/mi:text-fg";

  return (
    <div
      ref={menuRef}
      role="menu"
      style={style}
      className="fixed z-[90] flex min-w-[220px] animate-pop-in flex-col rounded-xl border-[0.5px] border-divider-strong bg-surface p-1.5 shadow-e3"
    >
      <div className="truncate px-3 pb-2 pt-2.5 font-mono text-[11.5px] tracking-[-0.005em] text-muted" title={user.email}>
        {user.email}
      </div>
      {/* 管理コンソールへの導線（org admin / 部門管理者のみ）。チャットから離れる
          「目的地」なので、通常の操作項目より一段格上げしてカード状に見せる。 */}
      {onOpenAdmin && (
        <>
          <button
            className="group/admin mb-1 flex w-full items-center gap-2.5 rounded-[9px] border-[0.5px] border-divider bg-accent-soft px-2 py-2 text-left transition-colors hover:border-divider-strong"
            role="menuitem"
            onClick={onOpenAdmin}
          >
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-[8px] bg-accent text-white">
              <Icon name="building" size={14} />
            </span>
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="truncate text-[12.5px] font-semibold leading-tight text-fg">{t.sidebar.adminConsole}</span>
              <span className="truncate text-[10.5px] leading-tight text-muted">{t.sidebar.adminConsoleHint}</span>
            </span>
            <Icon name="chevronRight" size={14} className="shrink-0 text-muted-2 transition-transform group-hover/admin:translate-x-0.5" />
          </button>
          <div className="my-1 h-px bg-divider" />
        </>
      )}
      {onOpenSettings && (
        <button className={itemCls} role="menuitem" onClick={onOpenSettings}>
          <span className={iconCls}>
            <Icon name="cog" size={14} />
          </span>
          <span className="min-w-0 flex-1">{t.sidebar.settings}</span>
          <span className="text-[11px] text-muted-2">
            <kbd className="border-0 bg-transparent p-0 text-muted-2">{SHORTCUT_LABEL.settings}</kbd>
          </span>
        </button>
      )}
      <button className={itemCls} role="menuitem" onClick={onToggleTheme}>
        <span className={iconCls}>
          <Icon name={dark ? "sun" : "moon"} size={14} />
        </span>
        <span className="min-w-0 flex-1">{dark ? t.sidebar.lightMode : t.sidebar.darkMode}</span>
      </button>
      {onOpenWorkCalendar && (
        <button className={itemCls} role="menuitem" onClick={onOpenWorkCalendar}>
          <span className={iconCls}>
            <Icon name="calendar" size={14} />
          </span>
          <span className="min-w-0 flex-1">{t.sidebar.workCalendar}</span>
        </button>
      )}
      {onOpenHelp && (
        <button className={itemCls} role="menuitem" onClick={onOpenHelp}>
          <span className={iconCls}>
            <svg viewBox="0 0 16 16" width="14" height="14" fill="none">
              <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.4" />
              <path d="M6 6.5a2 2 0 014 0c0 .8-.5 1.2-1 1.5s-1 .5-1 1.2M8 11.4v.1" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
            </svg>
          </span>
          <span className="min-w-0 flex-1">{t.sidebar.showHelp}</span>
          <span className="text-[11px] text-muted-2">
            <kbd className="border-0 bg-transparent p-0 text-muted-2">?</kbd>
          </span>
        </button>
      )}
      {onSignOut && (
        <>
          <div className="mx-1.5 my-1 h-px bg-divider" />
          <button className={itemCls} role="menuitem" onClick={onSignOut}>
            <span className={iconCls}>
              <Icon name="signout" size={14} />
            </span>
            <span className="min-w-0 flex-1">{t.sidebar.signOut}</span>
          </button>
        </>
      )}
    </div>
  );
}
