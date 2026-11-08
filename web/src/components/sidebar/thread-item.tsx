"use client";

// chat サイドバー（sidebar.tsx）と agents サイドバー（Task 5 で AgentSidebar が利用）で
// 共有する ThreadRow / ThreadMenu。文案は呼び出し側が labels prop で注入する（useT を
// 内部で呼ばない）ため、chat 固有の日本語/中国語 i18n にも agents 側の純中国語文案にも
// 同じコンポーネントで対応できる。

import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Icon } from "@/components/icons";
import { cn } from "@/lib/utils";
import type { ThreadSummary } from "@/lib/types";

export interface ThreadItemLabels {
  /** 「⋯」按钮 aria-label */
  menuLabel: string;
  star: string;
  unstar: string;
  rename: string;
  delete: string;
  /** 未提供则菜单不渲染该项 */
  addToProject?: string;
}

export interface ThreadRowProps {
  thread: ThreadSummary;
  active: boolean;
  renaming: boolean;
  renameValue: string;
  menuOpen: boolean;
  labels: ThreadItemLabels;
  onRenameChange: (v: string) => void;
  onRenameCommit: () => void;
  onRenameCancel: () => void;
  onSelect: () => void;
  onOpenMenu: (rect: { left: number; top: number; bottom: number; right: number }) => void;
  /** 行尾追加节点（如 agents 侧栏的运行中脉冲圆点）。未提供则不渲染此槽位——
   *  chat 侧沿用旧行为零变化，只有传入方（agents）会在布局中多出这一层。 */
  trailing?: ReactNode;
}

export function ThreadRow({
  thread, active, renaming, renameValue, menuOpen, labels, trailing,
  onRenameChange, onRenameCommit, onRenameCancel,
  onSelect, onOpenMenu,
}: ThreadRowProps) {
  if (renaming) {
    return (
      <div className="my-px flex w-full items-center gap-2 rounded-md bg-surface px-2 py-1 shadow-e1">
        {thread.pinned && (
          <span className="shrink-0 text-accent">
            <Icon name="starFilled" size={11} />
          </span>
        )}
        <input
          autoFocus
          value={renameValue}
          onChange={(e) => onRenameChange(e.target.value)}
          onBlur={onRenameCommit}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              onRenameCommit();
            } else if (e.key === "Escape") {
              e.preventDefault();
              onRenameCancel();
            }
          }}
          className="min-w-0 flex-1 border-0 bg-transparent py-1 text-[12.5px] text-fg outline-none"
        />
      </div>
    );
  }

  return (
    <div
      className={cn(
        "group/row relative my-px flex w-full items-stretch rounded-md transition-colors",
        active ? "bg-surface shadow-e1" : "bg-transparent hover:bg-divider",
        menuOpen && "bg-divider",
      )}
    >
      <button
        title={thread.title}
        onClick={onSelect}
        className={cn(
          "flex min-w-0 flex-1 items-center gap-2 rounded-md py-1.5 pl-2 pr-8 text-left text-[12.5px] transition-colors",
          // 選択強調は色のみ（font-weight を上げると CJK が合成太字でちぐはぐになるため使わない）。
          active ? "text-fg" : "text-fg-2",
        )}
      >
        {thread.pinned && (
          <span className="shrink-0 text-accent">
            <Icon name="starFilled" size={11} />
          </span>
        )}
        <span className="min-w-0 flex-1 truncate">{thread.title}</span>
      </button>
      {active && (
        <span
          className={cn(
            "pointer-events-none absolute right-3 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-accent transition-opacity",
            "group-hover/row:opacity-0",
            menuOpen && "opacity-0",
          )}
        />
      )}
      {trailing && !active && (
        // active 圆点と同じ位置（right-3）を再利用——両方 true になる行は無い想定
        // （active な会話は現在表示中なので、実行中でも上部「測算中」バッジで十分示せる）。
        <span
          className={cn(
            "pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 transition-opacity",
            "group-hover/row:opacity-0",
            menuOpen && "opacity-0",
          )}
        >
          {trailing}
        </span>
      )}
      <button
        type="button"
        aria-label={labels.menuLabel}
        onClick={(e) => {
          e.stopPropagation();
          const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
          onOpenMenu({ left: rect.left, top: rect.top, bottom: rect.bottom, right: rect.right });
        }}
        className={cn(
          "absolute right-1 top-1/2 grid h-6 w-6 -translate-y-1/2 place-items-center rounded-md border-0 bg-transparent text-muted opacity-0 transition-opacity hover:bg-bg-2 hover:text-fg focus-visible:opacity-100 group-hover/row:opacity-100",
          menuOpen && "bg-bg-2 text-fg opacity-100",
        )}
      >
        <Icon name="more" size={13} />
      </button>
    </div>
  );
}

export interface ThreadMenuItemsProps {
  thread: ThreadSummary;
  labels: ThreadItemLabels;
  onStar: () => void;
  onRename: () => void;
  onDelete: () => void;
  /** labels.addToProject と同時に提供されたときだけ「添加到项目」項目を出す。 */
  onAddProject?: () => void;
}

/**
 * メニュー項目一覧のみを描く hook 無しの純粋子コンポーネント。
 * ThreadMenu は定位/開閉副作用（useRef/useState/useEffect）を持つため直接テストできない。
 * こちらは副作用を持たないので、関数を直接呼んでテストできる。
 */
export function ThreadMenuItems({ thread, labels, onStar, onRename, onDelete, onAddProject }: ThreadMenuItemsProps) {
  const itemCls =
    "group/mi flex w-full items-center gap-3 rounded-[7px] border-0 bg-transparent px-2.5 py-2 text-left text-[13px] text-fg transition-colors hover:bg-divider";
  const iconCls = "inline-flex w-[18px] shrink-0 items-center justify-center text-muted group-hover/mi:text-fg";

  return (
    <>
      <button className={itemCls} role="menuitem" onClick={onStar}>
        <span className={iconCls}>
          <Icon name={thread.pinned ? "starFilled" : "star"} size={14} />
        </span>
        <span className="min-w-0 flex-1">{thread.pinned ? labels.unstar : labels.star}</span>
      </button>
      <button className={itemCls} role="menuitem" onClick={onRename}>
        <span className={iconCls}>
          <Icon name="pencil" size={14} />
        </span>
        <span className="min-w-0 flex-1">{labels.rename}</span>
      </button>
      {labels.addToProject && onAddProject && (
        <button className={itemCls} role="menuitem" onClick={onAddProject}>
          <span className={iconCls}>
            <Icon name="inbox" size={14} />
          </span>
          <span className="min-w-0 flex-1">{labels.addToProject}</span>
        </button>
      )}
      <div className="mx-1.5 my-1 h-px bg-divider" />
      <button
        className={cn(itemCls, "text-[#B83A1F] hover:bg-[#FDEFEA] dark:hover:bg-[rgba(184,58,31,0.16)]")}
        role="menuitem"
        onClick={onDelete}
      >
        <span className="inline-flex w-[18px] shrink-0 items-center justify-center text-[#B83A1F]">
          <Icon name="trash" size={14} />
        </span>
        <span className="min-w-0 flex-1">{labels.delete}</span>
      </button>
    </>
  );
}

export interface ThreadMenuProps {
  thread: ThreadSummary;
  anchor: { left: number; top: number; bottom: number; right: number };
  labels: ThreadItemLabels;
  onClose: () => void;
  onStar: () => void;
  onRename: () => void;
  onDelete: () => void;
  /** labels.addToProject と同時に提供されたときだけ渲染 */
  onAddProject?: () => void;
}

export function ThreadMenu({ thread, anchor, labels, onClose, onStar, onRename, onAddProject, onDelete }: ThreadMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const [style, setStyle] = useState<React.CSSProperties>(() => ({
    left: anchor.right + 4,
    top: anchor.top,
    width: 200,
    visibility: "hidden",
  }));

  // Re-position after mount: prefer right of trigger, fall back to left or below.
  useEffect(() => {
    const el = menuRef.current;
    if (!el) return;
    const { offsetWidth: w, offsetHeight: h } = el;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let left = anchor.right + 4;
    if (left + w > vw - 8) left = Math.max(8, anchor.left - w - 4);
    let top = anchor.top;
    if (top + h > vh - 8) top = Math.max(8, vh - h - 8);
    setStyle({ left, top, width: w });
  }, [anchor]);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (menuRef.current?.contains(e.target as Node)) return;
      onClose();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <div
      ref={menuRef}
      role="menu"
      style={style}
      className="fixed z-[90] flex min-w-[200px] animate-pop-in flex-col rounded-xl border-[0.5px] border-divider-strong bg-surface p-1.5 shadow-e3"
    >
      <ThreadMenuItems
        thread={thread}
        labels={labels}
        onStar={onStar}
        onRename={onRename}
        onDelete={onDelete}
        onAddProject={onAddProject}
      />
    </div>
  );
}
