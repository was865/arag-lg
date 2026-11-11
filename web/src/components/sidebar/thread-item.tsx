"use client";

// chat サイドバー（sidebar.tsx）と agents サイドバー（Task 5 で AgentSidebar が利用）で
// 共有する ThreadRow / ThreadMenu。文案は呼び出し側が labels prop で注入する（useT を
// 内部で呼ばない）ため、chat 固有の日本語/中国語 i18n にも agents 側の純中国語文案にも
// 同じコンポーネントで対応できる。

import type { ReactNode } from "react";
import { Icon } from "@/components/icons";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/menu";
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
  onMenuOpenChange: (open: boolean) => void;
  /** 「⋯」メニューの中身（ThreadMenuItems）。開いているときだけ描かれる */
  menu?: ReactNode;
  /** 行尾追加节点（如 agents 侧栏的运行中脉冲圆点）。未提供则不渲染此槽位——
   *  chat 侧沿用旧行为零变化，只有传入方（agents）会在布局中多出这一层。 */
  trailing?: ReactNode;
}

export function ThreadRow({
  thread, active, renaming, renameValue, menuOpen, labels, trailing,
  onRenameChange, onRenameCommit, onRenameCancel,
  onSelect, onMenuOpenChange, menu,
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
      <Menu open={menuOpen} onOpenChange={onMenuOpenChange}>
        <MenuTrigger asChild>
          <button
            type="button"
            aria-label={labels.menuLabel}
            onClick={(e) => e.stopPropagation()}
            className={cn(
              "absolute right-1 top-1/2 grid h-6 w-6 -translate-y-1/2 place-items-center rounded-control border-0 bg-transparent text-muted opacity-0 outline-none transition-opacity hover:bg-bg-2 hover:text-fg focus-visible:opacity-100 group-hover/row:opacity-100",
              menuOpen && "bg-bg-2 text-fg opacity-100",
            )}
          >
            <Icon name="more" size={14} />
          </button>
        </MenuTrigger>
        <MenuContent
          side="right"
          align="start"
          className="min-w-[200px] p-1.5"
          // 「名前を変更」で入力欄にフォーカスが移ったときは、ボタンへ戻さない（戻すと入力が確定してしまう）
          onCloseAutoFocus={(e) => {
            if (document.activeElement instanceof HTMLInputElement) e.preventDefault();
          }}
        >
          {menu}
        </MenuContent>
      </Menu>
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

/** 「⋯」メニューの項目。hook を持たないので関数を直接呼んでテストできる。 */
export function ThreadMenuItems({ thread, labels, onStar, onRename, onDelete, onAddProject }: ThreadMenuItemsProps) {
  return (
    <>
      <MenuItem icon={thread.pinned ? "starFilled" : "star"} onSelect={onStar}>
        {thread.pinned ? labels.unstar : labels.star}
      </MenuItem>
      <MenuItem icon="pencil" onSelect={onRename}>
        {labels.rename}
      </MenuItem>
      {labels.addToProject && onAddProject && (
        <MenuItem icon="inbox" onSelect={onAddProject}>
          {labels.addToProject}
        </MenuItem>
      )}
      <MenuSeparator />
      <MenuItem icon="trash" danger onSelect={onDelete}>
        {labels.delete}
      </MenuItem>
    </>
  );
}
