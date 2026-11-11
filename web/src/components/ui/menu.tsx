"use client";

/**
 * メニュー（UI 試作）。Radix DropdownMenu の上に、アプリ共通の見た目を載せる。
 * 位置合わせ（画面端での反転）・外側クリック・Esc・矢印キーでの移動・閉じたあとのフォーカス復帰は Radix が受け持つ。
 *
 *   <Menu>
 *     <MenuTrigger asChild><IconButton label="操作" icon="more" /></MenuTrigger>
 *     <MenuContent align="end">
 *       <MenuItem icon="pencil" onSelect={rename}>名前を変更</MenuItem>
 *       <MenuSeparator />
 *       <MenuItem icon="trash" danger onSelect={remove}>削除</MenuItem>
 *     </MenuContent>
 *   </Menu>
 */
import * as M from "@radix-ui/react-dropdown-menu";
import { Icon, type IconName } from "@/components/icons";
import { ICON } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const Menu = M.Root;
export const MenuTrigger = M.Trigger;
export const MenuGroup = M.Group;

/** 浮かぶ面（メニュー・ポップオーバー）の共通の見た目。ダイアログ（230 / 250）の上に出す */
export const floatingSurface =
  "z-[260] animate-pop-in rounded-card border-[0.5px] border-divider-strong bg-surface shadow-e3 outline-none motion-reduce:animate-none";

export function MenuContent({
  className,
  sideOffset = 6,
  collisionPadding = 8,
  ...props
}: React.ComponentProps<typeof M.Content>) {
  return (
    <M.Portal>
      <M.Content
        sideOffset={sideOffset}
        collisionPadding={collisionPadding}
        className={cn(floatingSurface, "flex min-w-[180px] flex-col p-1", className)}
        {...props}
      />
    </M.Portal>
  );
}

export function MenuItem({
  icon,
  danger,
  shortcut,
  hint,
  className,
  children,
  ...props
}: React.ComponentProps<typeof M.Item> & {
  icon?: IconName | React.ReactNode;
  /** 削除・停止など取り消しにくい操作 */
  danger?: boolean;
  /** 右端に出すキーボードショートカット */
  shortcut?: string;
  /** 2 行目の補足 */
  hint?: React.ReactNode;
}) {
  return (
    <M.Item
      className={cn(
        "group/mi flex cursor-default select-none items-center gap-2.5 rounded-control px-2.5 py-1.5 text-body text-fg outline-none",
        "data-[highlighted]:bg-divider data-[disabled]:pointer-events-none data-[disabled]:opacity-45",
        danger && "text-danger data-[highlighted]:bg-danger-soft",
        hint && "items-start",
        className,
      )}
      {...props}
    >
      {icon !== undefined && (
        <span
          className={cn(
            "inline-flex w-4 shrink-0 items-center justify-center",
            danger ? "text-danger" : "text-muted group-data-[highlighted]/mi:text-fg",
            hint && "mt-0.5",
          )}
        >
          {typeof icon === "string" ? <Icon name={icon as IconName} size={ICON.md} /> : icon}
        </span>
      )}
      <span className="min-w-0 flex-1">
        {children}
        {hint && <span className="block text-caption text-muted">{hint}</span>}
      </span>
      {shortcut && <kbd className="border-0 bg-transparent p-0 font-sans text-caption text-muted-2">{shortcut}</kbd>}
    </M.Item>
  );
}

export function MenuSeparator({ className, ...props }: React.ComponentProps<typeof M.Separator>) {
  return <M.Separator className={cn("mx-1.5 my-1 h-px bg-divider", className)} {...props} />;
}

/** メニュー上部の見出し（メールアドレスなど、選べない文字） */
export function MenuLabel({ className, ...props }: React.ComponentProps<typeof M.Label>) {
  return <M.Label className={cn("truncate px-2.5 pb-1.5 pt-2 text-caption text-muted", className)} {...props} />;
}
