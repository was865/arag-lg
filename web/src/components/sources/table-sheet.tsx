"use client";

import { Dialog, DialogContent } from "@/components/ui/dialog";
import { useT } from "@/i18n/context";

/** 表を全画面で広く閲覧するためのシート。Esc / 背景タップ / ✕ で閉じる。 */
export function TableSheet({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  const { t } = useT();
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title={t.sources.tableSheetTitle} size="full">
        <div className="min-h-0 flex-1 overflow-auto border-t-[0.5px] border-divider p-4">{children}</div>
      </DialogContent>
    </Dialog>
  );
}
