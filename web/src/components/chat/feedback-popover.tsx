"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { useT } from "@/i18n/context";
import { FEEDBACK_REASON_TAGS, type FeedbackReasonTag } from "@/lib/feedback-types";

interface Props {
  initial: { reasonTags: FeedbackReasonTag[]; comment: string | null } | null;
  onSubmit: (v: { reasonTags: FeedbackReasonTag[]; comment: string }) => void;
  onClose: () => void;
}

/** 👎 押下時の理由タグ（複数選択）+ 任意コメントの軽量ポップオーバー。 */
export function FeedbackPopover({ initial, onSubmit, onClose }: Props) {
  const { t } = useT();
  const [tags, setTags] = useState<Set<FeedbackReasonTag>>(new Set(initial?.reasonTags ?? []));
  const [comment, setComment] = useState(initial?.comment ?? "");
  const ref = useRef<HTMLDivElement>(null);

  // 理由タグ → 表示ラベル。
  const labelOf: Record<FeedbackReasonTag, string> = {
    outdated: t.chat.feedbackReasonOutdated,
    wrong: t.chat.feedbackReasonWrong,
    no_source: t.chat.feedbackReasonNoSource,
    irrelevant: t.chat.feedbackReasonIrrelevant,
    other: t.chat.feedbackReasonOther,
  };

  // Escape と外側クリックで閉じる。
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onClose(); };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => { document.removeEventListener("keydown", onKey); document.removeEventListener("mousedown", onDown); };
  }, [onClose]);

  function toggle(tag: FeedbackReasonTag) {
    setTags((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag); else next.add(tag);
      return next;
    });
  }

  return (
    <div
      ref={ref}
      role="dialog"
      className="absolute right-0 top-9 z-20 w-72 rounded-xl border-[0.5px] border-divider-strong bg-surface p-3.5 shadow-lg"
    >
      <p className="mb-2 text-[12.5px] font-semibold text-fg">{t.chat.feedbackDownReasonTitle}</p>
      <div className="mb-2.5 flex flex-wrap gap-1.5">
        {FEEDBACK_REASON_TAGS.map((tag) => (
          <button
            key={tag}
            type="button"
            onClick={() => toggle(tag)}
            className={cn(
              "rounded-full border-[0.5px] px-2.5 py-1 text-[11.5px] transition-colors",
              tags.has(tag)
                ? "border-accent bg-accent-soft text-accent"
                : "border-divider-strong bg-surface text-muted hover:text-fg",
            )}
          >
            {labelOf[tag]}
          </button>
        ))}
      </div>
      <textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder={t.chat.feedbackCommentPlaceholder}
        rows={2}
        maxLength={1000}
        className="mb-2.5 w-full resize-none rounded-lg border-[0.5px] border-divider-strong bg-surface-2 px-2.5 py-2 text-[12.5px] text-fg outline-none placeholder:text-muted focus:border-accent"
      />
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          className="rounded-md px-2.5 py-1 text-[12px] text-muted hover:text-fg"
        >
          {t.chat.feedbackCancel}
        </button>
        <button
          type="button"
          onClick={() => onSubmit({ reasonTags: [...tags], comment })}
          className="rounded-md bg-accent px-3 py-1 text-[12px] font-semibold text-white hover:opacity-90"
        >
          {t.chat.feedbackSubmit}
        </button>
      </div>
    </div>
  );
}
