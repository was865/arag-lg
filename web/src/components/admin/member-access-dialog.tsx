"use client";

/** あるメンバーが閲覧できる共有ナレッジベースと、その理由（specs/024 R13）。 */
import { useEffect, useState } from "react";
import { Icon } from "@/components/icons";
import { Dialog, DialogBody, DialogContent } from "@/components/ui/dialog";
import { useDepartments } from "@/hooks/use-departments";
import { accessApi, type UserKbAccess } from "@/lib/access/api";
import { reasonLabel, ROLE_LABEL } from "@/lib/access/shares";
import { ApiError } from "@/lib/chat/api";

export function MemberAccessDialog({ userId, name, onClose }: { userId: string; name: string; onClose: () => void }) {
  const { departments } = useDepartments();
  const [rows, setRows] = useState<UserKbAccess[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    accessApi.userAccess(userId).then(
      (r) => alive && setRows([...r].sort((a, b) => a.kb_name.localeCompare(b.kb_name, "ja"))),
      (e: unknown) => alive && setError(e instanceof ApiError ? e.message : "取得できませんでした"),
    );
    return () => {
      alive = false;
    };
  }, [userId]);

  const deptName = (id: string) => departments.find((d) => d.id === id)?.name ?? "（削除された部門）";

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        title={`${name} さんが閲覧できるナレッジベース`}
        description="共有のナレッジベースだけです。個人のナレッジベースは本人にしか見えません。"
        size="md"
        className="max-h-[80dvh]"
      >
        <DialogBody className="px-3">
          {error ? (
            <p className="m-0 rounded-control bg-danger-soft px-3 py-2 text-footnote text-danger">{error}</p>
          ) : rows === null ? (
            <div className="grid h-24 place-items-center">
              <span className="h-5 w-5 animate-[ar-spin_0.8s_linear_infinite] rounded-full border-2 border-divider-strong border-t-accent" />
            </div>
          ) : rows.length === 0 ? (
            <p className="py-10 text-center text-footnote text-muted">閲覧できる共有ナレッジベースはありません</p>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
              {rows.map((r) => (
                <li key={r.kb_id} className="flex items-start gap-3 rounded-control px-2 py-2 hover:bg-surface-2">
                  <Icon name="database" size={14} className="mt-0.5 shrink-0 text-muted" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-body font-medium text-fg">{r.kb_name}</div>
                    <ul className="m-0 list-none p-0">
                      {r.reasons.map((x) => (
                        <li key={`${x.subject_type}:${x.subject_id}`} className="text-caption text-muted">
                          {reasonLabel(x, deptName)}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <span className="shrink-0 rounded-full bg-surface-2 px-2 py-0.5 text-caption font-medium text-fg-2">
                    {ROLE_LABEL[r.role]}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
