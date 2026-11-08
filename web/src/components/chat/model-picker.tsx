"use client";

// ModelPicker：Composer の「モデル」ボタンに錨定するモデル選択ポップオーバー。
// 視覚は ScopePicker と同系（surface / divider-strong / shadow-e3 / pop-in / 下向き矢印）。
// 設定モーダルを開かずその場で切替できる軽量経路として、chat / agents の双方から使う。

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import type { ModelOption } from "@/lib/types";
import { useT } from "@/i18n/context";

interface Props {
  open: boolean;
  /** 錨定先（Composer のモデルボタン）。ポップオーバーはこの直上に出す。 */
  anchorRef: React.RefObject<HTMLButtonElement | null>;
  models: ModelOption[];
  /** 現在選択中のモデル id。 */
  value: string;
  onChange: (model: ModelOption) => void;
  onClose: () => void;
}

export function ModelPicker({ open, anchorRef, models, value, onChange, onClose }: Props) {
  const [pos, setPos] = useState({ right: 0, bottom: 0 });
  const { t } = useT();

  // モデルボタンは Composer 右端にあるため右揃えで配置する（ScopePicker は左揃え）。
  useEffect(() => {
    if (!open || !anchorRef.current) return;
    const r = anchorRef.current.getBoundingClientRect();
    setPos({ right: Math.max(8, window.innerWidth - r.right), bottom: window.innerHeight - r.top + 6 });
  }, [open, anchorRef]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    const onDown = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest(".model-pop") && !anchorRef.current?.contains(target)) onClose();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onDown);
    };
  }, [open, onClose, anchorRef]);

  if (!open) return null;

  return (
    <div
      className="model-pop fixed z-[150] flex max-h-[420px] w-[280px] animate-pop-in flex-col overflow-hidden rounded-[14px] border-[0.5px] border-divider-strong bg-surface shadow-e3 max-md:w-[min(280px,calc(100vw-20px))]"
      style={{ right: pos.right, bottom: pos.bottom }}
    >
      <span className="absolute -bottom-[6px] right-[18px] h-2.5 w-2.5 rotate-45 border-b-[0.5px] border-r-[0.5px] border-divider-strong bg-surface" />
      <div className="border-b-[0.5px] border-divider px-3.5 py-2.5 text-[12px] font-semibold text-muted">
        {t.modals.navModel}
      </div>
      <div className="overflow-y-auto p-1.5">
        {models.map((m) => {
          const active = m.id === value;
          // API キー未設定のモデルは選択不可（理由はツールチップと「未設定」バッジで示す）。
          const unavailable = m.available === false;
          return (
            <button
              key={m.id}
              type="button"
              disabled={unavailable}
              title={unavailable ? t.modals.modelUnavailableHint : undefined}
              onClick={() => {
                onChange(m);
                onClose();
              }}
              className={cn(
                "flex w-full items-center gap-2.5 rounded-lg border-0 bg-transparent px-2.5 py-2 text-left transition-colors",
                unavailable ? "cursor-not-allowed opacity-50" : active ? "bg-accent-soft" : "hover:bg-divider",
              )}
            >
              <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", active ? "bg-accent" : "bg-divider-strong")} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="truncate text-[13px] font-semibold text-fg">{m.label}</span>
                  {m.tag && (
                    <span className="shrink-0 rounded-full border-[0.5px] border-accent/40 px-1.5 py-px text-[9.5px] font-bold text-accent">
                      {m.tag}
                    </span>
                  )}
                  {unavailable && (
                    <span className="shrink-0 rounded-full border-[0.5px] border-divider-strong px-1.5 py-px text-[9.5px] font-bold text-muted">
                      {t.modals.modelUnavailable}
                    </span>
                  )}
                </div>
                {m.desc && <div className="mt-px truncate text-[11px] text-muted">{m.desc}</div>}
              </div>
              {active && (
                <svg viewBox="0 0 16 16" width="12" height="12" className="text-accent">
                  <path d="M3 8l3.5 3.5L13 5" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
