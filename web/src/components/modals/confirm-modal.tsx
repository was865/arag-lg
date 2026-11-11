"use client";

import { useRef } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { useT } from "@/i18n/context";

export interface ConfirmModalProps {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "default" | "danger";
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmModal({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel,
  tone = "default",
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  const { t } = useT();
  // デフォルトラベルを辞書から取得（呼び出し元が明示的に渡した場合はそちらを優先）。
  const resolvedConfirmLabel = confirmLabel ?? t.modals.confirmDefaultLabel;
  const resolvedCancelLabel = cancelLabel ?? t.modals.cancelDefaultLabel;

  const confirmRef = useRef<HTMLButtonElement>(null);

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent
        alert
        layer="top"
        size="sm"
        title={title}
        description={description}
        // 開いたら確定ボタンにフォーカス（Enter でそのまま確定できる）
        onOpenAutoFocus={(e) => {
          e.preventDefault();
          confirmRef.current?.focus();
        }}
      >
        <DialogFooter>
          <Button size="lg" onClick={onCancel} className="h-9 text-body">
            {resolvedCancelLabel}
          </Button>
          <Button
            ref={confirmRef}
            size="lg"
            variant={tone === "danger" ? "danger" : "primary"}
            onClick={onConfirm}
            className="h-9 text-body"
          >
            {resolvedConfirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
