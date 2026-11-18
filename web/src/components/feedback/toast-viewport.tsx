"use client";

/**
 * トーストの表示（specs/025 R13）。重なった束で見せ、古いものは縮んで後ろへ下がる。
 * ポインタを乗せるかフォーカスを入れると束が広がり、全部を読める。位置の計算は lib/motion の stackStyle。
 */
import { useRef, useState } from "react";
import { AnimatePresence, m } from "motion/react";
import type { Toast } from "@/lib/types";
import { useT } from "@/i18n/context";
import { IconButton } from "@/components/ui/button";
import { DURATION, EASE, stackStyle } from "@/lib/motion";

interface Props {
  toasts: Toast[];
  onDismiss: (id: string) => void;
  /** 束にポインタやフォーカスがある間は自動で消さない */
  onPause?: () => void;
  onResume?: () => void;
}

export function ToastViewport({ toasts, onDismiss, onPause, onResume }: Props) {
  const { t: dict } = useT();
  const [expanded, setExpanded] = useState(false);
  // 広げた束の隙間をポインタが通るたびに閉じないよう、少し待ってから閉じる
  const leaveTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const open = () => {
    clearTimeout(leaveTimer.current);
    setExpanded(true);
    onPause?.();
  };
  const close = () => {
    clearTimeout(leaveTimer.current);
    leaveTimer.current = setTimeout(() => {
      setExpanded(false);
      onResume?.();
    }, 150);
  };
  const isOpen = expanded && toasts.length > 1;
  return (
    // モバイルの下端オフセットは CSS 変数 --ar-toast-bottom で制御する。既定は
    // safe-area + 12px（admin/login など下部に障害物の無い画面向け）。コンポーザーを
    // 持つ workspace はマウント中に変数を上書きしてコンポーザーを避ける。
    // 子はすべて同じ格子のマスに重ね、y と拡大で束にする。
    <section
      aria-label={dict.feedback.regionLabel}
      onPointerEnter={open}
      onPointerLeave={close}
      onFocus={open}
      onBlur={close}
      className="pointer-events-none fixed bottom-6 left-1/2 z-[200] grid -translate-x-1/2 items-end justify-items-center max-md:bottom-[var(--ar-toast-bottom,calc(env(safe-area-inset-bottom)+12px))] max-md:left-3 max-md:right-3 max-md:translate-x-0"
    >
      <AnimatePresence initial={false}>
        {toasts.map((t, i) => {
          const index = toasts.length - 1 - i;
          const s = stackStyle(index, isOpen);
          return (
            <m.div
              key={t.id}
              initial={{ opacity: 0, y: 24, scale: 0.96 }}
              animate={{ opacity: s.opacity, y: s.y, scale: s.scale }}
              exit={{ opacity: 0, scale: 0.96, transition: { duration: DURATION.exit, ease: EASE.in } }}
              aria-hidden={s.hidden || undefined}
              style={{ zIndex: 10 - index, gridArea: "1 / 1" }}
              className={
                "inline-flex min-w-[240px] max-w-[420px] origin-bottom items-center gap-2.5 card py-2.5 pl-[14px] pr-3 text-body font-medium text-fg shadow-e2 max-md:w-full max-md:min-w-0 max-md:max-w-none " +
                (s.hidden ? "pointer-events-none" : "pointer-events-auto")
              }
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
            </m.div>
          );
        })}
      </AnimatePresence>
    </section>
  );
}
