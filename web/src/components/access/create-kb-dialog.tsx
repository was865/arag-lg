"use client";

/** 共有のナレッジベースを作る（specs/024 R9）。admin は全員向け・部門向け、部門管理者は自分の部門向け。 */
import { useState } from "react";
import { useToast } from "@/components/feedback/toast-provider";
import { Button } from "@/components/ui/button";
import { ChoiceList } from "@/components/ui/choice";
import { Dialog, DialogBody, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { accessApi, type DepartmentOut } from "@/lib/access/api";
import { ApiError } from "@/lib/chat/api";

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
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="ナレッジベースを作成" size="sm">
        <form onSubmit={submit} className="flex min-h-0 flex-col">
          <DialogBody className="flex flex-col gap-4 pb-1">
            <Field label="名前">
              <Input
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={200}
                placeholder="設備保全マニュアル"
              />
            </Field>
            <div className="grid gap-1.5">
              <span className="text-footnote font-medium text-fg-2">公開範囲</span>
              <ChoiceList
                label="公開範囲"
                value={dept}
                options={options.map((o) => ({
                  id: o.id,
                  label: o.label,
                  hint: o.hint,
                  icon: o.id ? "group" : "building",
                }))}
                onChange={setDept}
              />
            </div>
            <p className="m-0 text-caption text-muted">
              作ったあなたが「管理」になります。あとから「共有」で、部門や人を足したり、編集できる人を決めたりできます。
            </p>
          </DialogBody>
          <DialogFooter>
            <Button onClick={onClose}>キャンセル</Button>
            <Button type="submit" variant="primary" disabled={!name.trim() || saving || options.length === 0}>
              {saving ? "作成しています…" : "作成"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
