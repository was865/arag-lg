"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/icons";
import { useKbs } from "@/hooks/use-kbs";
import { cn } from "@/lib/utils";
import type { ScopePreset, ScopeValue } from "@/lib/types";
import { useT } from "@/i18n/context";

interface Props {
  open: boolean;
  anchorRef: React.RefObject<HTMLButtonElement | null>;
  value: ScopeValue;
  onChange: (scope: ScopeValue) => void;
  onClose: () => void;
  attachmentCount: number;
}

export function ScopePicker({ open, anchorRef, value, onChange, onClose, attachmentCount }: Props) {
  const [pos, setPos] = useState({ left: 0, bottom: 0 });
  const { t } = useT();
  // 旧版のプリセット（全社・Wiki・Slack など）は実在しないデータソースだったので、添付だけを残す
  const scopePresets: ScopePreset[] = [
    { id: "files", label: t.chat.scopeFilesOnly, iconName: "paperclip", desc: t.chat.scopeFilesOnlyDesc, sources: ["uploads"] },
  ];
  const { kbs } = useKbs();

  // 検索範囲セレクタ用の KB 行: 「全て」 + アクセスできる実 KB。kbId が retrieve に反映される。
  const allKbsScope: ScopeValue = {
    id: "kb:all", label: t.chat.scopeAllKbs, iconName: "folders",
    desc: t.chat.scopeAllKbsDesc, sources: [], kbId: null,
  };
  const kbScope = (kb: { id: string; kind: string; name: string }): ScopeValue => ({
    id: `kb:${kb.id}`,
    label: kb.kind === "personal" ? t.chat.scopePersonalKb : kb.name,
    iconName: kb.kind === "personal" ? "user" : "database",
    sources: [], kbId: kb.id,
  });

  useEffect(() => {
    if (!open || !anchorRef.current) return;
    const r = anchorRef.current.getBoundingClientRect();
    setPos({ left: r.left, bottom: window.innerHeight - r.top + 6 });
  }, [open, anchorRef]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    const onDown = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest(".scope-pop") && !anchorRef.current?.contains(target)) onClose();
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
      className="scope-pop fixed z-[150] flex max-h-[480px] w-[340px] animate-pop-in flex-col overflow-hidden rounded-[14px] border-[0.5px] border-divider-strong bg-surface shadow-e3 max-md:max-h-[60vh] max-md:w-[min(340px,calc(100vw-20px))] max-md:max-w-[calc(100vw-20px)]"
      style={{ left: pos.left, bottom: pos.bottom }}
    >
      <span className="absolute -bottom-[6px] left-[18px] h-2.5 w-2.5 rotate-45 border-b-[0.5px] border-r-[0.5px] border-divider-strong bg-surface" />
      <div className="flex items-center justify-between border-b-[0.5px] border-divider px-3.5 py-2.5 text-[12px] font-semibold text-muted">
        <span>{t.chat.scopeHeader}</span>
        <kbd>⌘K</kbd>
      </div>
      <div className="overflow-y-auto p-1.5">
        {/* 実検索範囲 = ナレッジベース。ここの選択だけが retrieve の kb_ids に反映される。 */}
        <div className="px-2.5 pb-1 pt-2 text-[10px] font-bold uppercase tracking-[0.07em] text-muted-2">{t.chat.scopeKbSection}</div>
        {[{ scope: allKbsScope, archived: false }, ...kbs.map((kb) => ({ scope: kbScope(kb), archived: kb.status === "archived" }))].map(({ scope: s, archived }) => {
          const active = value.id === s.id;
          return (
            <button
              key={s.id}
              onClick={() => { onChange({ ...s, includeArchived: value.includeArchived }); onClose(); }}
              className={cn(
                "flex w-full items-center gap-2.5 rounded-lg border-0 bg-transparent px-2.5 py-2 text-left transition-colors",
                active ? "bg-accent-soft" : "hover:bg-divider",
              )}
            >
              <span className={cn("inline-flex w-4 items-center justify-center", active ? "text-accent" : "text-muted")}>
                <Icon name={s.iconName} size={15} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="truncate text-[13px] font-semibold text-fg">{s.label}</span>
                  {/* archived KB は既定検索から外れるが、明示選択すれば検索される（バックエンドが補完）。
                      利用者が「なぜ全体検索に出ないか」を理解できるよう状態を明示する。 */}
                  {archived && (
                    <span className="shrink-0 rounded-full border-[0.5px] border-divider-strong px-1.5 py-px text-[9.5px] font-bold uppercase tracking-[0.04em] text-muted-2">
                      {t.chat.scopeArchivedBadge}
                    </span>
                  )}
                </div>
                {s.desc && <div className="mt-px truncate text-[11px] text-muted">{s.desc}</div>}
              </div>
              {active && (
                <svg viewBox="0 0 16 16" width="12" height="12" className="text-accent">
                  <path d="M3 8l3.5 3.5L13 5" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
            </button>
          );
        })}

        <div className="mx-1 my-1.5 h-px bg-divider" />

        {/* アーカイブも検索トグル（KB 検索範囲に作用するため KB セクション直下に置き、
            プリセットでスクロールアウトせず常に見える位置にする）。 */}
        <button
          onClick={() => {
            onChange({ ...value, includeArchived: !value.includeArchived });
          }}
          className="flex w-full items-center gap-2.5 rounded-lg border-0 bg-transparent px-2.5 py-2 text-left hover:bg-divider"
        >
          <span
            className={cn(
              "relative inline-flex h-[16px] w-[28px] shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors",
              value.includeArchived ? "bg-accent" : "bg-divider-strong",
            )}
          >
            <span
              className={cn(
                "inline-block h-[12px] w-[12px] rounded-full bg-white shadow-sm transition-transform",
                value.includeArchived ? "translate-x-[12px]" : "translate-x-0",
              )}
            />
          </span>
          <span className="min-w-0 flex-1 truncate text-[13px] font-semibold text-fg">{t.chat.scopeIncludeArchived}</span>
        </button>

        <div className="mx-1 my-1.5 h-px bg-divider" />

        {scopePresets.map((p) => {
          const isFiles = p.id === "files";
          const disabled = isFiles && !attachmentCount;
          const active = value.id === p.id;
          return (
            <button
              key={p.id}
              disabled={disabled}
              onClick={() => {
                // includeArchived は検索範囲の修飾子なので KB/プリセット選択をまたいで保持する。
                onChange({ ...p, includeArchived: value.includeArchived });
                onClose();
              }}
              className={cn(
                "flex w-full items-center gap-2.5 rounded-lg border-0 bg-transparent px-2.5 py-2 text-left transition-colors",
                active && "bg-accent-soft",
                disabled ? "cursor-not-allowed opacity-50" : "hover:bg-divider",
              )}
            >
              <span className={cn("inline-flex w-4 items-center justify-center", active ? "text-accent" : "text-muted")}>
                <Icon name={p.iconName} size={15} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 text-[13px] font-semibold text-fg">
                  {p.label}
                  {isFiles && attachmentCount > 0 && (
                    <span className="rounded-full border-[0.5px] border-accent/40 px-1.5 py-px font-mono text-[9.5px] font-bold text-accent">
                      {attachmentCount}
                    </span>
                  )}
                </div>
                <div className="mt-px text-[11px] text-muted">{disabled ? t.chat.noFilesUploaded : p.desc}</div>
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
