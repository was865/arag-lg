"use client";

/** 共有のナレッジベースを作る（specs/024 R9）。admin は全員向け・部門向け、部門管理者は自分の部門向け。 */
import { useEffect, useState } from "react";
import { Icon } from "@/components/icons";
import { useToast } from "@/components/feedback/toast-provider";
import { accessApi, type DepartmentOut } from "@/lib/access/api";
import { ApiError } from "@/lib/chat/api";
import { cn } from "@/lib/utils";

export function CreateKbDialog({
  isAdmin,
  departments,
  onClose,
  onCreated,
}: {
  isAdmin: boolean;
  /** 選べる部門（admin はすべて、部門管理者は自分が管理する部門）。 */
  departments: DepartmentOut[];
  onClose: () => void;
  onCreated: (kbId: string) => void;
}) {
  const push = useToast();
  const [name, setName] = useState("");
  // null = 社内の全員（admin だけ）
  const [dept, setDept] = useState<string | null>(isAdmin ? null : (departments[0]?.id ?? null));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || saving) return;
    setSaving(true);
    try {
      const kb = await accessApi.createKb(name.trim(), dept);
      push("ナレッジベースを作成しました", "success");
      onCreated(kb.id);
    } catch (err) {
      push(err instanceof ApiError ? err.message : "作成できませんでした", "error");
    } finally {
      setSaving(false);
    }
  };

  const options: { id: string | null; label: string; hint: string }[] = [
    ...(isAdmin ? [{ id: null, label: "社内の全員", hint: "全員が閲覧できます" }] : []),
    ...departments.map((d) => ({ id: d.id, label: d.name, hint: `部門の ${d.member_count} 名が閲覧できます` })),
  ];

  return (
    <div
      className="fixed inset-0 z-[240] grid animate-overlay-in place-items-center bg-[rgba(20,18,15,0.35)] p-6 max-md:items-end max-md:p-0"
      onClick={onClose}
    >
      <form
        role="dialog"
        aria-modal="true"
        aria-label="ナレッジベースを作成"
        onSubmit={submit}
        onClick={(e) => e.stopPropagation()}
        className="flex w-[440px] max-w-full animate-pop-in flex-col gap-4 rounded-[16px] border-[0.5px] border-divider-strong bg-surface p-5 shadow-e3 max-md:w-full max-md:rounded-[18px_18px_0_0] max-md:pb-[max(16px,env(safe-area-inset-bottom))]"
      >
        <div className="flex items-center gap-2">
          <h3 className="m-0 flex-1 text-[15px] font-bold text-fg">ナレッジベースを作成</h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="閉じる"
            className="grid h-7 w-7 place-items-center rounded-md text-muted hover:bg-divider hover:text-fg"
          >
            <Icon name="close" size={13} />
          </button>
        </div>
        <label className="grid gap-1.5 text-[12px] text-muted">
          名前
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={200}
            placeholder="設備保全マニュアル"
            className="h-9 rounded-lg border-[0.5px] border-divider-strong bg-surface px-3 text-[13px] text-fg outline-none placeholder:text-muted-2 focus:border-accent"
          />
        </label>
        <fieldset className="m-0 grid gap-1.5 border-0 p-0">
          <legend className="mb-1.5 p-0 text-[12px] text-muted">公開範囲</legend>
          {options.map((o) => (
            <label
              key={o.id ?? "everyone"}
              className={cn(
                "flex cursor-pointer items-center gap-2.5 rounded-lg border-[0.5px] px-3 py-2",
                dept === o.id ? "border-accent bg-accent-soft" : "border-divider-strong hover:bg-divider",
              )}
            >
              <input type="radio" name="kb-target" checked={dept === o.id} onChange={() => setDept(o.id)} className="accent-[var(--accent)]" />
              <Icon name={o.id ? "group" : "building"} size={14} className="text-muted" />
              <span className="min-w-0 flex-1">
                <span className="block text-[13px] text-fg">{o.label}</span>
                <span className="block text-[11.5px] text-muted">{o.hint}</span>
              </span>
            </label>
          ))}
        </fieldset>
        <p className="m-0 text-[11.5px] leading-[1.6] text-muted">
          作ったあなたが「管理」になります。あとから「共有」で、部門や人を足したり、編集できる人を決めたりできます。
        </p>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="h-8 rounded-lg border-[0.5px] border-divider-strong px-3 text-[12.5px] font-medium text-fg hover:bg-divider"
          >
            キャンセル
          </button>
          <button
            type="submit"
            disabled={!name.trim() || saving || options.length === 0}
            className="h-8 rounded-lg bg-accent px-3.5 text-[12.5px] font-semibold text-white hover:brightness-105 disabled:opacity-50"
          >
            {saving ? "作成しています…" : "作成"}
          </button>
        </div>
      </form>
    </div>
  );
}
