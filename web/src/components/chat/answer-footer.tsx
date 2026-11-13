"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { IconButton, Button } from "@/components/ui/button";
import type { FeedbackReasonTag, TurnFeedback } from "@/lib/feedback-types";
import { useT } from "@/i18n/context";
import { FeedbackPopover } from "@/components/chat/feedback-popover";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/ui/menu";

/** トークン数の短い表示（1000 以上は k）。 */
export function formatTokens(tokens: number): string {
  return tokens >= 1000 ? `${(tokens / 1000).toFixed(1).replace(/\.0$/, "")}k` : String(tokens);
}

interface Props {
  tokens: number;
  durationMs: number;
  onCopy: () => void;
  onDownload: () => void;
  onDownloadHtml: () => void;
  onRegenerate: () => void;
  /** 👍 トグル、または 👎/👍 を取り消す（同 rating 再押下）。 */
  onFeedback: (v: "up" | "down") => void;
  /** 👎 の詳細（理由タグ + コメント）送信。 */
  onFeedbackDetail: (v: { reasonTags: FeedbackReasonTag[]; comment: string }) => void;
  feedback: TurnFeedback | null;
  /** messageId 未確定（保存前ライブ）なら操作不可。 */
  feedbackDisabled?: boolean;
}

/**
 * 回答の下の操作。常に見せるのは「コピー・再生成・良い・良くない・その他」の 5 つ（specs/028 R8）。
 * 保存 2 つと所要時間・トークン（技術的な情報）は「その他」のメニューに入れる。
 */
export function AnswerFooter({ tokens, durationMs, onCopy, onDownload, onDownloadHtml, onRegenerate, onFeedback, onFeedbackDetail, feedback, feedbackDisabled }: Props) {
  const { t } = useT();
  const [popoverOpen, setPopoverOpen] = useState(false);

  function handleDown() {
    if (feedbackDisabled) return;
    // 既に down のときは取り消し。それ以外は理由ポップオーバーを開く。
    if (feedback?.rating === "down") onFeedback("down");
    else setPopoverOpen(true);
  }
  return (
    <div className="mt-1 flex items-center justify-end gap-0.5">
      <IconButton label={t.chat.copyTitle} onClick={onCopy}>
        <svg viewBox="0 0 16 16" width="12" height="12">
          <rect x="5" y="3" width="9" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.4" fill="none" />
          <path d="M3 11V4.5A1.5 1.5 0 014.5 3H10" stroke="currentColor" strokeWidth="1.4" fill="none" />
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
      <Menu>
        <MenuTrigger asChild>
          <IconButton label={t.chat.moreActions} icon="more" iconSize={12} />
        </MenuTrigger>
        <MenuContent align="end" side="top">
          <MenuItem icon="download" onSelect={onDownload}>{t.chat.saveMarkdown}</MenuItem>
          <MenuItem icon="code" onSelect={onDownloadHtml}>{t.chat.saveHtml}</MenuItem>
          <MenuSeparator />
          <dl className="m-0 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 px-2.5 py-1.5 text-footnote">
            <dt className="text-muted">{t.chat.answerDetailTime}</dt>
            <dd className="nums m-0 text-right font-mono text-fg">{(durationMs / 1000).toFixed(1)} 秒</dd>
            <dt className="text-muted">{t.chat.answerDetailTokens}</dt>
            <dd className="nums m-0 text-right font-mono text-fg">{formatTokens(tokens)}</dd>
          </dl>
        </MenuContent>
      </Menu>
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

/** 回答の数字のうち、資料・計算結果に見当たらなかったもの（specs/026 R16）。 */
export function UnverifiedNumbersNotice({ numbers }: { numbers: string[] }) {
  const { t } = useT();
  if (numbers.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 rounded-card border-[0.5px] border-divider-strong bg-surface-2 px-3.5 py-2 text-footnote text-muted">
      <svg viewBox="0 0 16 16" width="14" height="14" className="shrink-0" aria-hidden>
        <path d="M8 2.5l6 10.5H2z" stroke="currentColor" strokeWidth="1.3" fill="none" strokeLinejoin="round" />
        <path d="M8 6.5v3M8 11.2v.1" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
      <strong className="font-semibold text-fg">{t.chat.unverifiedNumbers}</strong>
      {numbers.slice(0, 8).map((n) => (
        <span key={n} className="rounded-control border-[0.5px] border-divider-strong bg-surface px-1.5 py-px font-mono text-caption tabular-nums text-fg">
          {n}
        </span>
      ))}
      <span>{t.chat.unverifiedNumbersHint}</span>
    </div>
  );
}

/** 数字の照合のステップ（system / number_check）から、見当たらなかった数字を取り出す。 */
export function unverifiedNumbers(steps: { name: string; input: Record<string, unknown>; output: Record<string, unknown> | null }[]): string[] {
  const check = steps.findLast((s) => s.name === "system" && s.input.kind === "number_check");
  const list = check?.output?.unverified;
  return Array.isArray(list) ? list.map(String) : [];
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
