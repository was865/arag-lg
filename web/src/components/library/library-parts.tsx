/** 文書ライブラリの小さな部品（行の名前の変更・行のメニュー・選択の印・空のとき・まとめて操作の帯）。 */
import { Button, IconButton } from "@/components/ui/button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/menu";
import { Icon, type IconName } from "@/components/icons";
import { cn } from "@/lib/utils";
import { t } from "@/i18n";
import { interpolate } from "@/i18n/interpolate";

/** 一覧の列（名前・状態・ページ・サイズ・追加日・メニュー）。見出しの行と各行で同じものを使う */
export const ROW_GRID =
  "grid grid-cols-[minmax(0,1fr)_120px_70px_80px_64px_32px] items-center gap-3 max-md:grid-cols-[minmax(0,1fr)_32px] max-md:gap-2";

/** ライブラリ内のドラッグ（文書の移動）。OS からのファイルのドロップと区別する。 */
export const DOC_MIME = "application/x-arag-document";

export function FolderIcon() {
  return (
    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-control bg-accent-soft text-accent">
      <Icon name="folder" size={15} />
    </span>
  );
}

export function RenameInput({
  value,
  onChange,
  onCommit,
  onCancel,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  onCommit: () => void;
  onCancel: () => void;
  placeholder?: string;
}) {
  return (
    <input
      autoFocus
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      onBlur={onCommit}
      onKeyDown={(e) => {
        if (e.nativeEvent.isComposing) return;
        if (e.key === "Enter") onCommit();
        if (e.key === "Escape") onCancel();
      }}
      className="w-full rounded-control border-[0.5px] border-accent bg-surface px-1.5 py-0.5 text-body text-fg outline-none"
    />
  );
}

export interface RowMenuItem {
  label: string;
  icon: IconName;
  onClick: () => void;
  danger?: boolean;
}

export function RowMenu({ open, onToggle, items }: { open: boolean; onToggle: (open: boolean) => void; items: RowMenuItem[] }) {
  return (
    <span data-row-menu className="justify-self-end">
      <Menu open={open} onOpenChange={onToggle}>
        <MenuTrigger asChild>
          <IconButton
            label={t.library.rowMenu}
            icon="more"
            tooltip={false}
            className={cn(!open && "opacity-0 focus-visible:opacity-100 group-hover/row:opacity-100 max-md:opacity-100")}
          />
        </MenuTrigger>
        {/* ポータルの中のクリックも React では行まで伝わるので、行の選択・遷移に届かないよう止める */}
        <MenuContent align="end" data-row-menu onClick={(e) => e.stopPropagation()}>
          {items.map((it) => (
            <MenuItem key={it.label} icon={it.icon} danger={it.danger} onSelect={it.onClick}>
              {it.label}
            </MenuItem>
          ))}
        </MenuContent>
      </Menu>
    </span>
  );
}

export function EmptyLibrary({ canUpload, onPick }: { canUpload: boolean; onPick: () => void }) {
  return (
    <div className="grid place-items-center px-6 py-16">
      <button
        type="button"
        disabled={!canUpload}
        onClick={onPick}
        className="flex w-full max-w-[520px] flex-col items-center gap-3 rounded-[16px] border-2 border-dashed border-divider-strong bg-surface-2 px-8 py-12 text-center enabled:hover:border-accent enabled:hover:bg-accent-soft disabled:cursor-default"
      >
        <span className="grid h-12 w-12 place-items-center rounded-sheet bg-accent-soft text-accent">
          <Icon name="database" size={20} />
        </span>
        <span className="text-headline font-semibold text-fg">
          {canUpload ? t.library.emptyTitle : t.library.emptyReadOnly}
        </span>
        {canUpload && (
          <span className="text-footnote leading-[1.6] text-muted">
            {t.library.emptyHint}
            <br />
            {t.library.emptyFormats}
          </span>
        )}
      </button>
    </div>
  );
}

export function CheckBox({ checked }: { checked: boolean }) {
  return (
    <span
      aria-hidden
      className={cn(
        "grid h-[18px] w-[18px] place-items-center rounded-control border-[1.5px]",
        checked ? "border-accent-fill bg-accent-fill text-white" : "border-divider-strong bg-surface text-transparent",
      )}
    >
      <Icon name="check" size={11} />
    </span>
  );
}

export function BulkBar({
  count,
  total,
  busy,
  canMove,
  canRemove,
  onSelectAll,
  onMove,
  onRemove,
  onClear,
}: {
  count: number;
  total: number;
  busy: boolean;
  canMove: boolean;
  canRemove: boolean;
  onSelectAll: () => void;
  onMove: () => void;
  onRemove: () => void;
  onClear: () => void;
}) {
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[6] flex justify-center px-3 pb-[max(14px,env(safe-area-inset-bottom))]">
      <div
        role="toolbar"
        aria-label={t.library.bulkToolbar}
        className="pointer-events-auto flex max-w-full animate-pop-in items-center gap-1 rounded-sheet border-[0.5px] border-divider-strong bg-surface p-1.5 pl-3.5 shadow-e3"
      >
        <span className="mr-1 shrink-0 whitespace-nowrap text-footnote font-semibold text-fg">
          {interpolate(t.library.selectedCount, { count })}
        </span>
        <Button variant="ghost" onClick={onSelectAll} disabled={busy || count === total} className="text-fg-2 max-md:hidden">
          {t.library.selectAll}
        </Button>
        <Button variant="ghost" onClick={onMove} disabled={busy || count === 0 || !canMove}>
          <Icon name="folder" size={13} />
          {t.library.move}
        </Button>
        <Button variant="danger-ghost" onClick={onRemove} disabled={busy || !canRemove}>
          <Icon name="trash" size={13} />
          {t.library.toTrashShort}
        </Button>
        <IconButton label={t.library.clearSelection} tooltip={false} icon="close" onClick={onClear} className="h-8 w-8" />
      </div>
    </div>
  );
}
