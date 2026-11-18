"use client";

/** 文書の移動先フォルダを選ぶダイアログ。木を字下げして並べ、今いる場所は選べない。 */
import { Icon } from "@/components/icons";
import { ICON } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent } from "@/components/ui/dialog";
import type { FolderOut } from "@/lib/library/api";
import { folderOptions } from "@/lib/library/folders";
import { cn } from "@/lib/utils";
import { t } from "@/i18n";

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
  const options = [
    { id: null as string | null, name: rootLabel, depth: 0, root: true },
    ...folderOptions(folders).map((f) => ({ id: f.id as string | null, name: f.name, depth: f.depth + 1, root: false })),
  ];

  return (
    <Dialog open onOpenChange={(o) => !o && onCancel()}>
      <DialogContent title={title} size="sm" className="max-h-[70vh]">
        <DialogBody className="px-1.5 pb-[max(6px,env(safe-area-inset-bottom))]">
          {options.map((o) => {
            const here = o.id === current;
            return (
              <button
                key={o.id ?? "root"}
                type="button"
                disabled={here}
                onClick={() => onPick(o.id)}
                style={{ paddingLeft: 10 + o.depth * 16 }}
                className={cn(
                  "flex w-full items-center gap-2 rounded-control py-2 pr-2.5 text-left text-body",
                  here ? "cursor-default text-muted-2" : "text-fg hover:bg-divider",
                )}
              >
                <Icon name={o.root ? "database" : "folder"} size={ICON.md} />
                <span className="min-w-0 flex-1 truncate">{o.name}</span>
                {here && <span className="shrink-0 text-caption">{t.library.currentLocation}</span>}
              </button>
            );
          })}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
