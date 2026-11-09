"use client";

/** 文書の移動先フォルダを選ぶダイアログ。木を字下げして並べ、今いる場所は選べない。 */
import { useEffect } from "react";
import { Icon } from "@/components/icons";
import type { FolderOut } from "@/lib/library/api";
import { folderOptions } from "@/lib/library/folders";
import { cn } from "@/lib/utils";

export interface MoveDialogProps {
  title: string;
  folders: FolderOut[];
  /** いまの場所（null = ルート直下、undefined = 決まっていない＝どこでも選べる）。 */
  current?: string | null;
  rootLabel: string;
  onPick: (folderId: string | null) => void;
  onCancel: () => void;
}

export function MoveDialog({ title, folders, current, rootLabel, onPick, onCancel }: MoveDialogProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onCancel();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel]);

  const options = [
    { id: null as string | null, name: rootLabel, depth: 0, root: true },
    ...folderOptions(folders).map((f) => ({ id: f.id as string | null, name: f.name, depth: f.depth + 1, root: false })),
  ];

  return (
    <div
      className="fixed inset-0 z-[240] grid animate-overlay-in place-items-center bg-[rgba(20,18,15,0.35)] p-6 max-md:items-end max-md:p-0"
      onClick={onCancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[70vh] w-[420px] max-w-full animate-pop-in flex-col rounded-[16px] border-[0.5px] border-divider-strong bg-surface shadow-e3 max-md:w-full max-md:rounded-[18px_18px_0_0]"
      >
        <div className="flex items-center gap-2 border-b-[0.5px] border-divider px-4 py-3">
          <h3 className="m-0 min-w-0 flex-1 truncate text-[14px] font-bold text-fg">{title}</h3>
          <button
            onClick={onCancel}
            aria-label="閉じる"
            className="grid h-7 w-7 place-items-center rounded-md text-muted hover:bg-divider hover:text-fg"
          >
            <Icon name="close" size={13} />
          </button>
        </div>
        <div className="min-h-0 overflow-y-auto p-1.5 pb-[max(6px,env(safe-area-inset-bottom))]">
          {options.map((o) => {
            const here = o.id === current;
            return (
              <button
                key={o.id ?? "root"}
                disabled={here}
                onClick={() => onPick(o.id)}
                style={{ paddingLeft: 10 + o.depth * 16 }}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md py-2 pr-2.5 text-left text-[13px]",
                  here ? "cursor-default text-muted-2" : "text-fg hover:bg-divider",
                )}
              >
                <Icon name={o.root ? "database" : "folder"} size={14} />
                <span className="min-w-0 flex-1 truncate">{o.name}</span>
                {here && <span className="shrink-0 text-[11px]">現在の場所</span>}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
