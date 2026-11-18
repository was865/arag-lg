/** 文書ライブラリの行（フォルダ・文書）。状態は持たず、表示と操作の受け渡しだけをする。 */
import { Badge } from "@/components/ui/badge";
import { fileTileStyle } from "@/components/ui/file-tile";
import { Spinner } from "@/components/ui/spinner";
import { Icon } from "@/components/icons";
import { CheckBox, DOC_MIME, FolderIcon, ROW_GRID, RenameInput, RowMenu } from "@/components/library/library-parts";
import { getFileMeta } from "@/lib/file-types";
import { originalUrl, type DocumentOut, type FolderOut } from "@/lib/library/api";
import { docStatus, formatBytes, formatDate, type StatusTone } from "@/lib/library/view";
import { cn } from "@/lib/utils";
import { t } from "@/i18n";
import { interpolate } from "@/i18n/interpolate";

const TONE: Record<StatusTone, string> = {
  ok: "text-muted",
  busy: "text-accent",
  danger: "text-danger",
  muted: "text-muted-2",
};

/** 名前を変えている最中の入力（その行を変えていなければ渡さない） */
export interface RenameState {
  value: string;
  onChange: (v: string) => void;
  onCommit: () => void;
  onCancel: () => void;
  placeholder?: string;
}

function NameInput({ rename }: { rename: RenameState }) {
  return <RenameInput {...rename} />;
}

/** 一覧の列見出し */
export function ListHeader() {
  return (
    <div className={cn(ROW_GRID, "eyebrow border-b-[0.5px] border-divider px-2 py-2 max-md:hidden")}>
      <span>{t.library.colName}</span>
      <span>{t.library.colStatus}</span>
      <span className="text-right">{t.library.colPages}</span>
      <span className="text-right">{t.library.colSize}</span>
      <span className="text-right">{t.library.colAdded}</span>
      <span />
    </div>
  );
}

/** 新しいフォルダの名前を入れる行 */
export function NewFolderRow({ rename }: { rename: RenameState }) {
  return (
    <div className={cn(ROW_GRID, "rounded-control px-2 py-2")}>
      <div className="flex min-w-0 items-center gap-2.5">
        <FolderIcon />
        <span className="w-full max-w-[360px]">
          <NameInput rename={rename} />
        </span>
      </div>
    </div>
  );
}

export function FolderRow({
  folder: f,
  rename,
  canEdit,
  menuOpen,
  onMenuToggle,
  dropProps,
  dropActive,
  onOpen,
  onStartRename,
  onRemove,
}: {
  folder: FolderOut;
  rename: RenameState | null;
  canEdit: boolean;
  menuOpen: boolean;
  onMenuToggle: (open: boolean) => void;
  /** 文書をこのフォルダへ落として移す props */
  dropProps: React.HTMLAttributes<HTMLDivElement>;
  dropActive: boolean;
  onOpen: () => void;
  onStartRename: () => void;
  onRemove: () => void;
}) {
  return (
    <div
      {...dropProps}
      className={cn(
        ROW_GRID,
        "group/row rounded-control px-2 py-2 hover:bg-surface-2",
        dropActive && "bg-accent-soft outline outline-1 outline-accent",
      )}
    >
      <div className="flex min-w-0 items-center gap-2.5">
        <FolderIcon />
        {rename ? (
          <NameInput rename={rename} />
        ) : (
          <button
            onClick={onOpen}
            title={f.name}
            className="min-w-0 flex-1 truncate text-left text-body font-medium text-fg hover:text-accent"
          >
            {f.name}
            <span className="ml-2 hidden font-normal text-muted max-md:inline">{interpolate(t.library.docCount, { document_count: f.document_count })}</span>
          </button>
        )}
      </div>
      <span className="text-footnote text-muted max-md:hidden">{interpolate(t.library.docCount, { document_count: f.document_count })}</span>
      <span className="max-md:hidden" />
      <span className="max-md:hidden" />
      <span className="text-right font-mono text-caption text-muted max-md:hidden">{formatDate(f.created_at)}</span>
      {canEdit ? (
        <RowMenu
          open={menuOpen}
          onToggle={onMenuToggle}
          items={[
            { label: t.library.open, icon: "folder", onClick: onOpen },
            { label: t.library.rename, icon: "pencil", onClick: onStartRename },
            { label: t.library.toTrash, icon: "trash", danger: true, onClick: onRemove },
          ]}
        />
      ) : (
        <span />
      )}
    </div>
  );
}

export function DocumentRow({
  doc: d,
  location,
  selecting,
  checked,
  movable,
  rename,
  menuOpen,
  onMenuToggle,
  onPick,
  onOpen,
  onRetry,
  onStartRename,
  onMove,
  onRemove,
}: {
  doc: DocumentOut;
  /** 名前の下に出す置き場（「すべて」では KB 名、絞り込み中はフォルダの道筋）。出さなければ null */
  location: { text: string; folder: boolean } | null;
  selecting: boolean;
  checked: boolean;
  /** フォルダへ移せるか（ドラッグ・メニューの「移動」） */
  movable: boolean;
  rename: RenameState | null;
  menuOpen: boolean;
  onMenuToggle: (open: boolean) => void;
  /** 選ぶ（shift で範囲） */
  onPick: (shift: boolean) => void;
  onOpen: () => void;
  onRetry: () => void;
  onStartRename: () => void;
  onMove: () => void;
  onRemove: () => void;
}) {
  const meta = getFileMeta(d.filename);
  const st = docStatus(d.status);
  const sep = location ? "· " : "";
  return (
    <div
      aria-selected={selecting ? checked : undefined}
      onClick={(e) => {
        if (!selecting) return;
        if ((e.target as HTMLElement).closest("[data-row-menu]")) return;
        e.preventDefault();
        onPick(e.shiftKey);
      }}
      draggable={!selecting && movable && !rename}
      onDragStart={(e) => {
        e.dataTransfer.setData(DOC_MIME, d.id);
        e.dataTransfer.effectAllowed = "move";
      }}
      className={cn(
        ROW_GRID,
        "group/row rounded-control px-2 py-2",
        selecting && "cursor-pointer select-none",
        checked ? "bg-accent-soft" : "hover:bg-surface-2",
      )}
    >
      <div className="flex min-w-0 items-center gap-2.5">
        <button
          type="button"
          role="checkbox"
          aria-checked={checked}
          aria-label={interpolate(t.library.pickDoc, { filename: d.filename })}
          onClick={(e) => {
            e.stopPropagation();
            onPick(e.shiftKey);
          }}
          className="group/check relative grid h-8 w-8 shrink-0 place-items-center rounded-control"
          style={selecting ? undefined : fileTileStyle(meta.color)}
        >
          {selecting ? (
            <CheckBox checked={checked} />
          ) : (
            <>
              <span className="group-hover/row:hidden max-md:!block">
                <Icon name={meta.iconName} size={15} />
              </span>
              <span className="hidden group-hover/row:block max-md:!hidden">
                <CheckBox checked={false} />
              </span>
            </>
          )}
        </button>
        <div className="min-w-0 flex-1">
          {rename ? (
            <NameInput rename={rename} />
          ) : (
            <button
              onClick={() => !selecting && onOpen()}
              title={d.filename}
              className="block max-w-full truncate text-left text-body font-medium text-fg hover:text-accent"
            >
              {d.filename}
            </button>
          )}
          <div className="flex items-center gap-1.5 truncate text-caption text-muted">
            {location &&
              (location.folder ? (
                <span className="inline-flex min-w-0 items-center gap-1 truncate">
                  <Icon name="folder" size={10} />
                  {location.text}
                </span>
              ) : (
                <span className="truncate">{location.text}</span>
              ))}
            {/* 検索できる文書がほとんどなので、状態はそれ以外のときだけ出す（specs/025 R46） */}
            {st.tone !== "ok" && (
              <span className={cn("hidden max-md:inline", TONE[st.tone])}>
                {sep}
                {st.label}
              </span>
            )}
            <span className="hidden max-md:inline">· {formatDate(d.created_at)}</span>
            {d.status === "ready" && d.chunk_count > 0 && (
              <span className="max-md:hidden">
                {interpolate(t.library.chunkCountSep, { sep, chunk_count: d.chunk_count.toLocaleString("ja-JP") })}
              </span>
            )}
            {d.status === "ready" && !!d.parse_warnings && (
              <Badge tone="danger" title={t.library.parseWarningsHint}>
                {interpolate(t.library.parseWarnings, { parse_warnings: d.parse_warnings })}
              </Badge>
            )}
          </div>
        </div>
      </div>
      <span className={cn("inline-flex items-center gap-1.5 text-footnote max-md:hidden", TONE[st.tone])}>
        {st.tone === "busy" && <Spinner />}
        {st.tone === "ok" ? <span className="sr-only">{st.label}</span> : st.label}
        {st.tone === "danger" && d.writable && d.job_id && (
          <button onClick={onRetry} className="ml-0.5 rounded px-1 text-caption font-semibold text-accent hover:underline">
            {t.library.retry}
          </button>
        )}
      </span>
      <span className="text-right font-mono text-caption text-muted max-md:hidden">{d.page_count ?? "—"}</span>
      <span className="text-right font-mono text-caption text-muted max-md:hidden">{formatBytes(d.size)}</span>
      <span className="text-right font-mono text-caption text-muted max-md:hidden">{formatDate(d.created_at)}</span>
      <RowMenu
        open={menuOpen}
        onToggle={onMenuToggle}
        items={[
          { label: t.library.openOriginal, icon: "external", onClick: () => window.open(originalUrl(d.id), "_blank", "noopener") },
          {
            label: t.common.download,
            icon: "download",
            onClick: () => {
              const a = document.createElement("a");
              a.href = originalUrl(d.id);
              a.download = d.filename;
              a.click();
            },
          },
          ...(d.writable
            ? [
                { label: t.library.rename, icon: "pencil" as const, onClick: onStartRename },
                ...(movable ? [{ label: t.library.moveTo, icon: "folder" as const, onClick: onMove }] : []),
                { label: t.library.toTrash, icon: "trash" as const, danger: true, onClick: onRemove },
              ]
            : []),
        ]}
      />
    </div>
  );
}
