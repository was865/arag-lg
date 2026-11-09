"use client";

/** 初回ガイド（specs/015-help-onboarding R5）: 4 ステップの案内。 */
import { useEffect, useState } from "react";
import { Icon } from "@/components/icons";
import { GUIDE_STEPS } from "@/lib/onboarding";
import { cn } from "@/lib/utils";

export function WelcomeGuide({ name, onClose }: { name?: string; onClose: () => void }) {
  const [i, setI] = useState(0);
  const step = GUIDE_STEPS[i];
  const last = i === GUIDE_STEPS.length - 1;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-[240] grid animate-overlay-in place-items-center bg-[rgba(20,18,15,0.45)] p-6 max-md:items-end max-md:p-0">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="welcome-title"
        className="flex w-[440px] max-w-full animate-pop-in flex-col overflow-hidden rounded-[16px] border-[0.5px] border-divider-strong bg-surface shadow-e3 max-md:w-full max-md:rounded-[18px_18px_0_0] max-md:pb-[env(safe-area-inset-bottom)]"
      >
        <div className="flex flex-col items-center gap-3 px-7 pb-5 pt-7 text-center">
          {i === 0 && (
            <p className="m-0 text-[12px] font-medium text-muted">{name ? `${name} さん、ようこそ` : "ようこそ"}</p>
          )}
          <span className="grid h-12 w-12 place-items-center rounded-[14px] bg-accent-soft text-accent">
            <Icon name={step.icon} size={22} />
          </span>
          <h2 id="welcome-title" className="m-0 text-[17px] font-bold text-fg">
            {step.title}
          </h2>
          <p className="m-0 min-h-[66px] text-[13px] leading-relaxed text-fg-2">{step.body}</p>
          <div className="flex gap-1.5" aria-label={`ステップ ${i + 1} / ${GUIDE_STEPS.length}`} role="img">
            {GUIDE_STEPS.map((s, n) => (
              <span
                key={s.title}
                className={cn("h-1.5 rounded-full transition-all", n === i ? "w-5 bg-accent" : "w-1.5 bg-divider-strong")}
              />
            ))}
          </div>
        </div>
        <footer className="flex items-center gap-2 border-t-[0.5px] border-divider px-5 py-3">
          <button
            onClick={onClose}
            className="h-8 rounded-lg px-2.5 text-[12.5px] font-medium text-muted hover:bg-divider hover:text-fg"
          >
            スキップ
          </button>
          <span className="flex-1" />
          {i > 0 && (
            <button
              onClick={() => setI(i - 1)}
              className="h-8 rounded-lg border-[0.5px] border-divider-strong bg-surface px-3 text-[12.5px] font-medium text-fg hover:bg-surface-2"
            >
              戻る
            </button>
          )}
          <button
            autoFocus
            onClick={() => (last ? onClose() : setI(i + 1))}
            className="h-8 rounded-lg bg-accent px-3.5 text-[12.5px] font-semibold text-white hover:brightness-105"
          >
            {last ? "はじめる" : "次へ"}
          </button>
        </footer>
      </div>
    </div>
  );
}
