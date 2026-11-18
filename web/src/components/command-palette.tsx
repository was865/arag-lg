"use client";

/**
 * コマンドパレット（⌘K。specs/025 R44）。スレッド（題名）・ナレッジベース・操作を 1 つの欄で絞り込み、Enter で移る。
 * 矢印キーで選び、Enter で実行、Esc で閉じる（フォーカスの閉じ込めと Esc は Dialog が受け持つ）。
 */
import { useMemo, useState } from "react";
import { Icon, type IconName } from "@/components/icons";
import { Dialog, DialogFrame } from "@/components/ui/dialog";
import { matchesQuery } from "@/lib/home";
import { cn } from "@/lib/utils";

export interface PaletteItem {
  id: string;
  group: string;
  label: string;
  icon?: IconName;
  /** icon の代わりに出す字標（ナレッジベース） */
  glyph?: string;
  /** 右端に出す補足（ショートカットなど） */
  hint?: string;
  run: () => void;
}

/** 1 つの群で出す件数の上限（スレッドが多くても一覧が流れないように） */
const GROUP_LIMIT = 8;

export function CommandPalette({ items, onClose }: { items: PaletteItem[]; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);

  const shown = useMemo(() => {
    const perGroup = new Map<string, number>();
    return items.filter((it) => {
      if (!matchesQuery(it.label, query)) return false;
      const n = perGroup.get(it.group) ?? 0;
      perGroup.set(it.group, n + 1);
      return n < GROUP_LIMIT;
    });
  }, [items, query]);
  const active = Math.min(cursor, Math.max(0, shown.length - 1));

  const run = (it: PaletteItem | undefined) => {
    if (!it) return;
    onClose();
    it.run();
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogFrame title="検索して移動" className="w-[560px] self-start mt-[12vh] max-md:mt-0 max-md:w-full max-md:self-end max-md:rounded-b-none">
        <div className="flex items-center gap-2.5 border-b-[0.5px] border-divider px-4">
          <span className="text-muted">
            <Icon name="search" size={14} />
          </span>
          <input
            autoFocus
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setCursor(0);
            }}
            onKeyDown={(e) => {
              if (e.nativeEvent.isComposing) return;
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setCursor((active + 1) % Math.max(1, shown.length));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setCursor((active - 1 + shown.length) % Math.max(1, shown.length));
              } else if (e.key === "Enter") {
                e.preventDefault();
                run(shown[active]);
              }
            }}
            role="combobox"
            aria-expanded
            aria-controls="command-palette-list"
            aria-activedescendant={shown[active] ? `palette-${shown[active].id}` : undefined}
            aria-label="スレッド・ナレッジベース・操作を探す"
            placeholder="スレッド・ナレッジベース・操作を探す"
            className="h-12 min-w-0 flex-1 border-0 bg-transparent text-callout text-fg outline-none placeholder:text-muted-2 max-md:text-[16px]"
          />
          <kbd className="text-mini">Esc</kbd>
        </div>
        <div id="command-palette-list" role="listbox" aria-label="候補" className="max-h-[min(420px,56vh)] overflow-y-auto p-1.5">
          {shown.length === 0 && <p className="m-0 px-3 py-6 text-center text-footnote text-muted">「{query}」に合うものはありません</p>}
          {shown.map((it, i) => (
            <div key={it.id}>
              {(i === 0 || shown[i - 1].group !== it.group) && (
                <div className="px-2.5 pb-1 pt-2 eyebrow">{it.group}</div>
              )}
              <div
                id={`palette-${it.id}`}
                role="option"
                aria-selected={i === active}
                onPointerMove={() => i !== active && setCursor(i)}
                onClick={() => run(it)}
                ref={(el) => {
                  if (el && i === active) el.scrollIntoView({ block: "nearest" });
                }}
                className={cn(
                  "flex cursor-pointer items-center gap-2.5 rounded-control px-2.5 py-2 text-body",
                  i === active ? "bg-fg text-bg" : "text-fg-2",
                )}
              >
                {it.glyph ? (
                  <span
                    aria-hidden
                    className={cn(
                      "grid h-[18px] w-[18px] shrink-0 place-items-center rounded-[5px] text-mini font-bold leading-none",
                      i === active ? "bg-bg text-fg" : "bg-divider-strong text-fg-2",
                    )}
                  >
                    {it.glyph}
                  </span>
                ) : (
                  <span className={cn("grid w-[18px] shrink-0 place-items-center", i === active ? "text-bg" : "text-muted")}>
                    <Icon name={it.icon ?? "chat"} size={14} />
                  </span>
                )}
                <span className="min-w-0 flex-1 truncate">{it.label}</span>
                {it.hint && <span className={cn("shrink-0 font-mono text-mini", i === active ? "text-bg/70" : "text-muted-2")}>{it.hint}</span>}
              </div>
            </div>
          ))}
        </div>
      </DialogFrame>
    </Dialog>
  );
}
