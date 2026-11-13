"use client";

import { useT } from "@/i18n/context";
import type { Turn } from "@/lib/types";

const MAX = 3;

/** 出す候補。最後のターン・完了・候補あり・実行中でない、のときだけ（specs/028 R6）。 */
export function followupsFor(
  turn: Turn,
  isLast: boolean,
  running: boolean,
): string[] {
  if (!isLast || running || turn.status !== "done") return [];
  return (turn.suggestions ?? []).slice(0, MAX);
}

/** 回答の下の「続けて聞く」。押すとその文をそのまま質問として送る。 */
export function Followups({
  items,
  onSend,
}: {
  items: string[];
  onSend: (text: string) => void;
}) {
  const { t } = useT();
  if (items.length === 0) return null;
  return (
    <div className="flex flex-col gap-1">
      <div className="text-caption text-muted">{t.chat.followupsTitle}</div>
      <FollowupRows items={items} onSend={onSend} />
    </div>
  );
}

/** 候補の行（縦に最大 3）。文書の札と同じく 50ms ずつずらして現れる。 */
export function FollowupRows({
  items,
  onSend,
}: {
  items: string[];
  onSend: (text: string) => void;
}) {
  return (
    <ul className="m-0 flex list-none flex-col p-0">
      {items.slice(0, MAX).map((q, i) => (
        <li
          key={q}
          className="animate-fade-up motion-reduce:animate-none"
          style={{ animationDelay: `${i * 50}ms` }}
        >
          <button
            type="button"
            onClick={() => onSend(q)}
            className="flex w-full items-baseline gap-2 rounded-control border-0 bg-transparent px-2 py-1.5 text-left text-callout text-fg-2 outline-none transition-colors duration-(--duration-mid) hover:bg-divider hover:text-fg focus-visible:ring-2 focus-visible:ring-accent/50 motion-reduce:transition-none"
          >
            <span aria-hidden className="shrink-0 text-footnote text-muted">
              ↳
            </span>
            <span className="min-w-0 break-words">{q}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
