"use client";

import type { Toast } from "@/lib/types";
import { useT } from "@/i18n/context";
import { IconButton } from "@/components/ui/button";

interface Props {
  toasts: Toast[];
  onDismiss: (id: string) => void;
}

export function ToastViewport({ toasts, onDismiss }: Props) {
  const { t: dict } = useT();
  return (
    // モバイルの下端オフセットは CSS 変数 --ar-toast-bottom で制御する。既定は
    // safe-area + 12px（admin/login など下部に障害物の無い画面向け）。コンポーザーを
    // 持つ workspace はマウント中に変数を上書きしてコンポーザーを避ける。
    <div className="pointer-events-none fixed bottom-6 left-1/2 z-[200] flex -translate-x-1/2 flex-col-reverse gap-2 max-md:bottom-[var(--ar-toast-bottom,calc(env(safe-area-inset-bottom)+12px))] max-md:left-3 max-md:right-3 max-md:translate-x-0">
      {toasts.map((t) => (
        <div
          key={t.id}
          className="pointer-events-auto inline-flex min-w-[240px] max-w-[420px] animate-toast-in items-center gap-2.5 rounded-card border-[0.5px] border-divider-strong bg-surface py-2.5 pl-[14px] pr-3 text-body font-medium text-fg shadow-e2 max-md:w-full max-md:min-w-0 max-md:max-w-none"
        >
          <span
            className={
              "shrink-0 " +
              (t.kind === "success" ? "text-accent" : t.kind === "error" ? "text-danger" : "text-muted")
            }
          >
            {t.kind === "success" && (
              <svg viewBox="0 0 16 16" width="14" height="14">
                <circle cx="8" cy="8" r="7" fill="currentColor" opacity="0.15" />
                <path d="M4.5 8.2 7 10.5l4.5-5" stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
            {t.kind === "info" && (
              <svg viewBox="0 0 16 16" width="14" height="14">
                <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.4" fill="none" />
                <path d="M8 7v4M8 5v.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            )}
            {t.kind === "error" && (
              <svg viewBox="0 0 16 16" width="14" height="14">
                <circle cx="8" cy="8" r="7" fill="currentColor" opacity="0.15" />
                <path d="M8 4v5M8 11v.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              </svg>
            )}
          </span>
          <span className="flex-1">{t.msg}</span>
          <IconButton size="icon-sm"
            onClick={() => onDismiss(t.id)}
            label={dict.feedback.closeAriaLabel}
          >
            <svg viewBox="0 0 12 12" width="10" height="10">
              <path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" />
            </svg>
          </IconButton>
        </div>
      ))}
    </div>
  );
}
