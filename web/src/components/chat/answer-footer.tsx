"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { IconButton, Button } from "@/components/ui/button";
import type { Source } from "@/lib/types";
import type { FeedbackReasonTag, TurnFeedback } from "@/lib/feedback-types";
import { useT } from "@/i18n/context";
import { FeedbackPopover } from "@/components/chat/feedback-popover";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

/** 出典チップの文言。引用した箇所の数と、その文書の数（同じ文書の別箇所を [1][2] と引くことがあるため）。 */
export function sourcesChipLabel(sources: Source[], t: { sourcesChip: string; sourcesChipDocs: string }): string | null {
  const passages = sources.reduce((n, s) => n + s.sections.length, 0);
  if (passages === 0) return null;
  const docs = sources.length;
  return (docs === passages ? t.sourcesChip : t.sourcesChipDocs)
    .replace("{n}", String(passages))
    .replace("{docs}", String(docs));
}

interface Props {
  tokens: number;
  durationMs: number;
  sources: Source[];
  onCopy: () => void;
  onDownload: () => void;
  onDownloadHtml: () => void;
  onRegenerate: () => void;
  onOpenSources: () => void;
  sourcesActive: boolean;
  /** 👍 トグル、または 👎/👍 を取り消す（同 rating 再押下）。 */
  onFeedback: (v: "up" | "down") => void;
  /** 👎 の詳細（理由タグ + コメント）送信。 */
  onFeedbackDetail: (v: { reasonTags: FeedbackReasonTag[]; comment: string }) => void;
  feedback: TurnFeedback | null;
  /** messageId 未確定（保存前ライブ）なら操作不可。 */
  feedbackDisabled?: boolean;
}

const chipCls =
  "inline-flex items-center gap-[5px] rounded-full border-[0.5px] border-divider-strong bg-surface px-2 py-[3px] font-mono text-caption text-muted";

export function AnswerFooter({ tokens, durationMs, sources, onCopy, onDownload, onDownloadHtml, onRegenerate, onOpenSources, sourcesActive, onFeedback, onFeedbackDetail, feedback, feedbackDisabled }: Props) {
  const { t } = useT();
  const sourcesLabel = sourcesChipLabel(sources, t.chat);
  const [popoverOpen, setPopoverOpen] = useState(false);

  function handleDown() {
    if (feedbackDisabled) return;
    // 既に down のときは取り消し。それ以外は理由ポップオーバーを開く。
    if (feedback?.rating === "down") onFeedback("down");
    else setPopoverOpen(true);
  }
  return (
    // 所要時間とトークン数は技術的な情報なので、普段は出さず「詳細」の中に入れる（specs/025 R45）
    <div className="mt-1 flex items-center justify-between gap-2 max-md:flex-wrap max-md:gap-y-2">
      <div className="flex flex-wrap gap-1.5">
        {sourcesLabel && (
        <button
          type="button"
          onClick={onOpenSources}
          title={t.chat.sourcesTitle}
          className={cn(
            chipCls,
            "cursor-pointer",
            sourcesActive
              ? "border-accent bg-accent-soft text-accent hover:bg-accent/20"
              : "hover:border-divider-strong hover:text-fg"
          )}
        >
          <svg viewBox="0 0 16 16" width="11" height="11">
            <path d="M5 2.75h6.25L13 4.5v7.75H5z" stroke="currentColor" strokeWidth="1.35" fill="none" strokeLinejoin="round" />
            <path d="M3 5.25v8h8" stroke="currentColor" strokeWidth="1.35" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M7 6.25h3.75M7 8.5h3.75" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
          {sourcesLabel}
        </button>
        )}
      </div>
      <div className="flex gap-0.5 max-md:ml-auto">
        <IconButton label={t.chat.copyTitle} onClick={onCopy}>
          <svg viewBox="0 0 16 16" width="12" height="12">
            <rect x="5" y="3" width="9" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.4" fill="none" />
            <path d="M3 11V4.5A1.5 1.5 0 014.5 3H10" stroke="currentColor" strokeWidth="1.4" fill="none" />
          </svg>
        </IconButton>
        <IconButton label={t.chat.downloadMarkdownTitle} onClick={onDownload}>
          <svg viewBox="0 0 16 16" width="12" height="12">
            <path d="M8 3v7M5 7.5L8 10.5l3-3M3.5 12.5h9" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </IconButton>
        <IconButton label={t.chat.downloadHtmlTitle} onClick={onDownloadHtml}>
          <svg viewBox="0 0 16 16" width="12" height="12">
            <path d="M2.5 3.5h11v9h-11z" stroke="currentColor" strokeWidth="1.3" fill="none" strokeLinejoin="round" />
            <path d="M2.5 6h11" stroke="currentColor" strokeWidth="1.3" />
            <path d="M4.3 4.7h.01M5.6 4.7h.01" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
          </svg>
        </IconButton>
        <IconButton label={t.chat.regenerateTitle} onClick={onRegenerate}>
          <svg viewBox="0 0 16 16" width="12" height="12">
            <path d="M13 8a5 5 0 11-1.5-3.5L13 6V3" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </IconButton>
        <IconButton
          label={t.chat.feedbackUpTitle}
          aria-pressed={feedback?.rating === "up"}
          className={cn(feedback?.rating === "up" && "text-accent hover:text-accent")}
          disabled={feedbackDisabled}
          onClick={() => onFeedback("up")}
        >
          <svg viewBox="0 0 16 16" width="12" height="12" fill={feedback?.rating === "up" ? "currentColor" : "none"}>
            <path d="M3 8h2v6H3zM5 8l3-5c0-1 1.5-1 1.5 0V7h3.5a1 1 0 011 1.3l-1.3 4a1 1 0 01-1 .7H5" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
          </svg>
        </IconButton>
        <FeedbackPopover
          open={popoverOpen}
          onOpenChange={setPopoverOpen}
          initial={feedback?.rating === "down" ? { reasonTags: feedback.reasonTags, comment: feedback.comment } : null}
          onSubmit={(v) => { onFeedbackDetail(v); setPopoverOpen(false); }}
        >
          <IconButton
            label={t.chat.feedbackDownTitle}
            aria-pressed={feedback?.rating === "down"}
            className={cn(feedback?.rating === "down" && "text-danger hover:text-danger")}
            disabled={feedbackDisabled}
            onClick={handleDown}
          >
            <svg viewBox="0 0 16 16" width="12" height="12" style={{ transform: "rotate(180deg)" }} fill={feedback?.rating === "down" ? "currentColor" : "none"}>
              <path d="M3 8h2v6H3zM5 8l3-5c0-1 1.5-1 1.5 0V7h3.5a1 1 0 011 1.3l-1.3 4a1 1 0 01-1 .7H5" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
            </svg>
          </IconButton>
        </FeedbackPopover>
        <Popover>
          <PopoverTrigger asChild>
            <IconButton label={t.chat.answerDetailTitle} icon="info" iconSize={12} />
          </PopoverTrigger>
          <PopoverContent align="end" side="top" className="w-[200px]">
            <dl className="m-0 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 px-3.5 py-3 text-footnote">
              <dt className="text-muted">{t.chat.answerDetailTime}</dt>
              <dd className="nums m-0 text-right font-mono text-fg">{(durationMs / 1000).toFixed(1)} 秒</dd>
              <dt className="text-muted">{t.chat.answerDetailTokens}</dt>
              <dd className="nums m-0 text-right font-mono text-fg">{tokens >= 1000 ? `${(tokens / 1000).toFixed(1).replace(/\.0$/, "")}k` : tokens}</dd>
            </dl>
          </PopoverContent>
        </Popover>
      </div>
    </div>
  );
}

export function CancelledNotice({ onRetry }: { onRetry: () => void }) {
  const { t } = useT();
  return (
    <div className="flex items-center gap-2.5 rounded-card border-[0.5px] border-dashed border-divider-strong bg-surface-2 px-3.5 py-2.5 text-body text-muted">
      <svg viewBox="0 0 16 16" width="14" height="14">
        <rect x="3" y="3" width="10" height="10" rx="2" stroke="currentColor" strokeWidth="1.4" fill="none" />
        <path d="M6 6l4 4M10 6l-4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
      <span>{t.chat.cancelledNotice}</span>
      <Button variant="plain" size="sm" className="ml-auto font-semibold" onClick={onRetry}>
        {t.chat.retryRun}
      </Button>
    </div>
  );
}

/** 資料を調べたのに引用の無い回答（小さいモデルで起きる）。内容を確かめるよう促す。 */
export function UncitedNotice() {
  const { t } = useT();
  return (
    <div className="flex items-start gap-2.5 rounded-card border-[0.5px] border-divider-strong bg-surface-2 px-3.5 py-2.5 text-footnote text-muted">
      <svg viewBox="0 0 16 16" width="14" height="14" className="mt-px shrink-0" aria-hidden>
        <path d="M8 2.5l6 10.5H2z" stroke="currentColor" strokeWidth="1.3" fill="none" strokeLinejoin="round" />
        <path d="M8 6.5v3M8 11.2v.1" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
      <span>
        <strong className="font-semibold text-fg">{t.chat.noAnswerUncited}</strong>
        {t.chat.noAnswerUncitedHint}
      </span>
    </div>
  );
}

/** 生成に失敗したターン（理由とやり直し）。 */
export function ErrorNotice({ message, onRetry }: { message?: string; onRetry: () => void }) {
  const { t } = useT();
  return (
    <div role="alert" className="flex items-center gap-2.5 rounded-card border-[0.5px] border-danger/40 bg-danger-soft px-3.5 py-2.5 text-body text-danger">
      <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden>
        <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.4" fill="none" />
        <path d="M8 4.8v3.6M8 10.8v.4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
      {/* 「モデルごとの理由」のように複数行で届くことがある */}
      <span className="min-w-0 flex-1 whitespace-pre-line [overflow-wrap:anywhere]">{message || t.chat.runFailedNotice}</span>
      <Button variant="plain" size="sm" className="font-semibold" onClick={onRetry}>
        {t.chat.retryRun}
      </Button>
    </div>
  );
}
