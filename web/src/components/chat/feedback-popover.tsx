"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverAnchor, PopoverClose, PopoverContent } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { useT } from "@/i18n/context";
import { FEEDBACK_REASON_TAGS, type FeedbackReasonTag } from "@/lib/feedback-types";
import { Textarea } from "@/components/ui/input";

interface Initial {
  reasonTags: FeedbackReasonTag[];
  comment: string | null;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 錨定先（👎 ボタン）。開くかどうかは呼び出し側が決める（取り消しのときは開かない） */
  children: React.ReactNode;
  initial: Initial | null;
  onSubmit: (v: { reasonTags: FeedbackReasonTag[]; comment: string }) => void;
}

/** 👎 押下時の理由タグ（複数選択）+ 任意コメントの軽量ポップオーバー。 */
export function FeedbackPopover({ open, onOpenChange, children, initial, onSubmit }: Props) {
  const { t } = useT();
  // Slot で子（ボタン）に渡るので、型は Anchor の既定（div）に合わせる
  const anchorRef = useRef<HTMLDivElement>(null);
  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverAnchor asChild ref={anchorRef}>
        {children}
      </PopoverAnchor>
      <PopoverContent
        side="bottom"
        align="end"
        aria-label={t.chat.feedbackDownReasonTitle}
        className="w-72 p-3.5"
        // 錨は Trigger ではないので、閉じたら自分で 👎 ボタンへフォーカスを戻す
        onCloseAutoFocus={(e) => {
          e.preventDefault();
          anchorRef.current?.focus();
        }}
      >
        {/* 閉じると中身ごと消えるので、開くたびに initial から始まる */}
        <FeedbackForm initial={initial} onSubmit={onSubmit} />
      </PopoverContent>
    </Popover>
  );
}

/** 報告の欄の中身（理由・コメント・共有の注意・送信）。 */
export function FeedbackForm({ initial, onSubmit }: { initial: Initial | null; onSubmit: Props["onSubmit"] }) {
  const { t } = useT();
  const [tags, setTags] = useState<Set<FeedbackReasonTag>>(new Set(initial?.reasonTags ?? []));
  const [comment, setComment] = useState(initial?.comment ?? "");

  // 理由タグ → 表示ラベル。
  const labelOf: Record<FeedbackReasonTag, string> = {
    outdated: t.chat.feedbackReasonOutdated,
    wrong: t.chat.feedbackReasonWrong,
    no_source: t.chat.feedbackReasonNoSource,
    irrelevant: t.chat.feedbackReasonIrrelevant,
    other: t.chat.feedbackReasonOther,
    error: t.chat.feedbackReasonError,
  };

  function toggle(tag: FeedbackReasonTag) {
    setTags((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag); else next.add(tag);
      return next;
    });
  }

  return (
    <>
      <p className="mb-2 text-footnote font-semibold text-fg">{t.chat.feedbackDownReasonTitle}</p>
      <div className="mb-2.5 flex flex-wrap gap-1.5">
        {FEEDBACK_REASON_TAGS.map((tag) => (
          <button
            key={tag}
            type="button"
            aria-pressed={tags.has(tag)}
            onClick={() => toggle(tag)}
            className={cn(
              "rounded-full border-[0.5px] px-2.5 py-1 text-caption transition-colors",
              tags.has(tag)
                ? "border-accent bg-accent-soft text-accent"
                : "border-divider-strong bg-surface text-muted hover:text-fg",
            )}
          >
            {labelOf[tag]}
          </button>
        ))}
      </div>
      <Textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder={t.chat.feedbackCommentPlaceholder}
        rows={2}
        maxLength={1000}
        className="mb-2.5 bg-surface-2"
      />
      {/* 送ると過程ごと管理者が読める（specs/028 R11） */}
      <p className="mb-2.5 text-caption text-muted">{t.chat.feedbackShareNote}</p>
      <div className="flex justify-end gap-2">
        <PopoverClose asChild>
          <Button variant="ghost" size="sm" className="text-muted">
            {t.chat.feedbackCancel}
          </Button>
        </PopoverClose>
        <Button variant="primary" size="sm"
          type="button"
          onClick={() => onSubmit({ reasonTags: [...tags], comment })}
        >
          {t.chat.feedbackSubmit}
        </Button>
      </div>
    </>
  );
}
