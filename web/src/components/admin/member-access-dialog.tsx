"use client";

/** あるメンバーが閲覧できる共有ナレッジベースと、その理由（specs/024 R13）。 */
import { useEffect, useState } from "react";
import { Icon } from "@/components/icons";
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

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const deptName = (id: string) => departments.find((d) => d.id === id)?.name ?? "（削除された部門）";

  return (
    <div
      className="fixed inset-0 z-[240] grid animate-overlay-in place-items-center bg-[rgba(20,18,15,0.35)] p-6 max-md:items-end max-md:p-0"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`${name} さんが閲覧できるナレッジベース`}
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[80dvh] w-[520px] max-w-full animate-pop-in flex-col gap-3 rounded-[16px] border-[0.5px] border-divider-strong bg-surface p-5 shadow-e3 max-md:w-full max-md:rounded-[18px_18px_0_0] max-md:pb-[max(16px,env(safe-area-inset-bottom))]"
      >
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <h3 className="m-0 truncate text-[15px] font-bold text-fg">{name} さんが閲覧できるナレッジベース</h3>
            <p className="m-0 mt-0.5 text-[11.5px] text-muted">共有のナレッジベースだけです。個人のナレッジベースは本人にしか見えません。</p>
          </div>
          <button
            onClick={onClose}
            aria-label="閉じる"
            className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-muted hover:bg-divider hover:text-fg"
          >
            <Icon name="close" size={13} />
          </button>
        </div>
        <div className="min-h-0 overflow-y-auto">
          {error ? (
            <p className="m-0 rounded-lg bg-danger-soft px-3 py-2 text-[12.5px] text-danger">{error}</p>
          ) : rows === null ? (
            <div className="grid h-24 place-items-center">
              <span className="h-5 w-5 animate-[ar-spin_0.8s_linear_infinite] rounded-full border-2 border-divider-strong border-t-accent" />
            </div>
          ) : rows.length === 0 ? (
            <p className="py-10 text-center text-[12.5px] text-muted">閲覧できる共有ナレッジベースはありません</p>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
              {rows.map((r) => (
                <li key={r.kb_id} className="flex items-start gap-3 rounded-lg px-2 py-2 hover:bg-surface-2">
                  <Icon name="database" size={14} className="mt-0.5 shrink-0 text-muted" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13px] font-medium text-fg">{r.kb_name}</div>
                    <ul className="m-0 list-none p-0">
                      {r.reasons.map((x) => (
                        <li key={`${x.subject_type}:${x.subject_id}`} className="text-[11.5px] text-muted">
                          {reasonLabel(x, deptName)}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <span className="shrink-0 rounded-full bg-surface-2 px-2 py-0.5 text-[11px] font-medium text-fg-2">
                    {ROLE_LABEL[r.role]}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
