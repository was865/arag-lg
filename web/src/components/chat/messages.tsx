"use client";

import { useState } from "react";
import { Button, IconButton } from "@/components/ui/button";
import { AnswerMarkdown } from "@/components/chat/answer-markdown";
import { AgentActivity } from "@/components/chat/agent-activity";
import { EvidenceRail } from "@/components/chat/evidence-rail";
import { evidenceList } from "@/lib/chat/evidence";
import { ActivityGlyph } from "@/components/chat/activity-glyph";
import {
  AnswerFooter,
  CancelledNotice,
  ErrorNotice,
  UncitedNotice,
  UnverifiedNumbersNotice,
  unverifiedNumbers,
} from "@/components/chat/answer-footer";
import { UserAttachments } from "@/components/uploads/uploads";
import type { CitationStyle, StagedFile, Turn, TurnImage, ToolView } from "@/lib/types";
import type { FeedbackReasonTag, TurnFeedback } from "@/lib/feedback-types";
import { useT } from "@/i18n/context";
import { Followups, followupsFor } from "@/components/chat/followups";
import { dateSeparator, formatTurnTimestamp, sameLocalDay } from "@/lib/datetime";

/** 質問に添えた画像の縮小表示。押すと拡大する（specs/017 R6）。 */
function QueryImageThumb({ image }: { image: TurnImage }) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const [broken, setBroken] = useState(false);
  if (broken) return <span className="text-footnote text-muted">{t.chat.imageAttached}</span>;
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title={t.chat.imageEnlarge}
        aria-label={t.chat.imageEnlarge}
        className="block overflow-hidden rounded-card border-0 bg-transparent p-0"
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- 認証つきの API 画像・data URL をそのまま出す */}
        <img
          src={image.url}
          alt={t.chat.imageAttached}
          width={image.width}
          height={image.height}
          onError={() => setBroken(true)}
          className="block h-auto max-h-[200px] w-auto max-w-[240px] object-contain"
        />
      </button>
      {open && (
        <div
          role="dialog"
          // eslint-disable-next-line no-restricted-syntax -- 画像の拡大表示（ライトボックス）。枠のない全面表示で、Esc は自前で処理する
          aria-modal="true"
          aria-label={t.chat.imageAttached}
          onClick={() => setOpen(false)}
          onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
          tabIndex={-1}
          ref={(el) => el?.focus()}
          className="fixed inset-0 z-50 grid place-items-center bg-[rgba(20,18,15,0.72)] p-4"
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- 拡大表示 */}
          <img src={image.url} alt={t.chat.imageAttached} className="max-h-full max-w-full rounded-card object-contain" />
        </div>
      )}
    </>
  );
}

export function UserMessage({
  text,
  time,
  onEdit,
  image,
}: {
  text: string;
  /** 質問に添えた画像（specs/017） */
  image?: TurnImage;
  time?: React.ReactNode;
  /** 指定すると、ホバーで「編集」を出し、送信で作り直す（R34）。 */
  onEdit?: (text: string) => void;
}) {
  const { t } = useT();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(text);
  if (editing && onEdit) {
    const submit = () => {
      const v = draft.trim();
      if (!v) return;
      setEditing(false);
      if (v !== text) onEdit(v);
    };
    return (
      <div className="flex justify-end">
        <div className="w-full max-w-[80%] rounded-[16px_16px_4px_16px] border-[0.5px] border-divider-strong bg-surface p-2.5 shadow-e1 max-md:max-w-[92%]">
          <textarea
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              } else if (e.key === "Escape") {
                setEditing(false);
              }
            }}
            rows={Math.min(8, Math.max(2, draft.split("\n").length))}
            aria-label={t.chat.editQuestion}
            className="w-full resize-none border-0 bg-transparent px-1.5 py-1 text-callout leading-[1.55] text-fg outline-none"
          />
          <div className="mt-1.5 flex items-center gap-2">
            <span className="min-w-0 flex-1 text-caption text-muted">{t.chat.editHint}</span>
            <Button variant="secondary" size="sm"
              onClick={() => { setEditing(false); setDraft(text); }}
            >{t.chat.editCancel}</Button>
            <Button variant="primary" size="sm"
              type="button"
              onClick={submit}
              disabled={!draft.trim()}
            >{t.chat.editSubmit}</Button>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="group flex items-end justify-end gap-2">
      {onEdit && (
        <IconButton
          label={t.chat.editQuestion}
          onClick={() => { setDraft(text); setEditing(true); }}
          className="order-first mb-1 opacity-0 focus-visible:opacity-100 group-hover:opacity-100 max-md:opacity-100"
        >
          <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden>
            <path d="M10.5 3.2l2.3 2.3-6.6 6.6-2.9.6.6-2.9 6.6-6.6z" stroke="currentColor" strokeWidth="1.3" fill="none" strokeLinejoin="round" />
          </svg>
        </IconButton>
      )}
      {/* 吹き出しを peer にし、ホバー時だけ時刻（order-first で左側）を出す。 */}
      <div className="peer max-w-[80%] whitespace-pre-wrap rounded-[16px_16px_4px_16px] bg-bubble-user px-4 py-3 text-callout leading-[1.55] text-bubble-user-fg [overflow-wrap:anywhere] max-md:max-w-[88%] max-md:rounded-[14px_14px_4px_14px] max-md:px-3.5 max-md:py-[11px] max-md:text-callout">
        {image && (
          <div className="mb-2">
            <QueryImageThumb image={image} />
          </div>
        )}
        {text}
      </div>
      {time}
    </div>
  );
}

/** ターン間の日付セパレータ（今日/昨日/月日）。 */
function DateSeparator({ label }: { label: string }) {
  return (
    <div className="my-1 flex items-center gap-3 text-caption text-muted max-md:my-0">
      <span className="h-px flex-1 bg-divider" />
      <span className="shrink-0">{label}</span>
      <span className="h-px flex-1 bg-divider" />
    </div>
  );
}

/**
 * アシスタントの発言。アバターは置かない: 右寄せの吹き出しが利用者、左端から始まる本文が回答、と位置だけで見分けが付く。
 * 先頭の「検索の過程」の行が回答の見出しを兼ねる（specs/025 R45）。
 */
export function AssistantMessage({ children }: { children: React.ReactNode }) {
  return <div className="flex min-w-0 flex-col gap-3.5 max-md:gap-3">{children}</div>;
}

/** 生成中の回答: 届いた文字が淡く現れ、末尾で印が呼吸する（specs/025 R20）。 */
export function StreamingAnswer({
  text,
  streaming,
  onCite,
  citationStyle,
}: {
  text: string;
  streaming: boolean;
  onCite: (n: number) => void;
  citationStyle: CitationStyle;
}) {
  return (
    <div className="text-callout text-fg-2">
      <AnswerMarkdown text={text} onCite={onCite} citationStyle={citationStyle} streaming={streaming} />
      {streaming && (
        <span className="ml-px inline-block h-4 w-2 animate-breathe rounded-[2px] bg-accent align-[-3px] motion-reduce:animate-none" />
      )}
    </div>
  );
}

export function StaticAnswer({
  text,
  onCite,
  citationStyle,
}: {
  text: string;
  onCite: (n: number) => void;
  citationStyle: CitationStyle;
}) {
  return (
    <div className="text-callout text-fg-2">
      <AnswerMarkdown text={text} onCite={onCite} citationStyle={citationStyle} />
    </div>
  );
}

export function Transcript({
  turns, toolView, expandedSteps, onToggleStep, onCite, citationStyle,
  onCopy, onDownload, onDownloadHtml, onRegenerate, onOpenSources, onFeedback, onFeedbackDetail, feedback,
  activeCiteTurn, rightPanelOpen, liveAttachments, isLiveLastTurn, onEdit, onFollowup,
}: {
  turns: Turn[];
  toolView: ToolView;
  expandedSteps: Record<string, boolean>;
  onToggleStep: (id: string) => void;
  // どのターンの引用かを特定するため turn index を渡す。
  onCite: (n: number, turnIdx: number) => void;
  citationStyle: CitationStyle;
  onCopy: (turnIdx: number) => void;
  onDownload: (turnIdx: number) => void;
  onDownloadHtml: (turnIdx: number) => void;
  onRegenerate: (turnIdx: number) => void;
  onOpenSources: (turnIdx: number) => void;
  onFeedback: (v: "up" | "down", turnIdx: number) => void;
  onFeedbackDetail: (v: { reasonTags: FeedbackReasonTag[]; comment: string }, turnIdx: number) => void;
  // 楽観的更新用の上書き（未設定なら turn.feedback にフォールバック）。
  feedback: Record<number, TurnFeedback | null>;
  activeCiteTurn: number;
  rightPanelOpen: boolean;
  liveAttachments: StagedFile[];
  isLiveLastTurn: boolean;
  /** 質問の編集→作り直し。未指定なら編集 UI を出さない（生成中など）。 */
  onEdit?: (turnIdx: number, text: string) => void;
  /** 続けて聞く候補を押したとき（specs/028）。未指定（生成中など）なら候補を出さない。 */
  onFollowup?: (text: string) => void;
}) {
  const { t } = useT();
  const now = new Date();
  return (
    <>
      {turns.map((turn, idx) => {
        const isLast = idx === turns.length - 1;
        const running = turn.status === "running";
        // 先頭、または前ターンと暦日が変わったら日付セパレータを挿入。
        const prev = turns[idx - 1];
        const showSeparator = !!turn.createdAt &&
          (idx === 0 || !prev?.createdAt || !sameLocalDay(new Date(prev.createdAt), new Date(turn.createdAt)));
        const sentTime = turn.createdAt ? formatTurnTimestamp(turn.createdAt) : "";
        return (
          <div key={idx} data-turn={idx} className="flex flex-col gap-6 max-md:gap-[18px]">
            {showSeparator && <DateSeparator label={dateSeparator(turn.createdAt!, now, { today: t.chat.dateToday, yesterday: t.chat.dateYesterday })} />}
            <UserMessage
              text={turn.query}
              image={turn.image}
              onEdit={onEdit && turn.messageId && !running ? (v) => onEdit(idx, v) : undefined}
              time={sentTime ? (
                <time
                  dateTime={turn.createdAt}
                  aria-label={t.chat.sentAt.replace("{time}", sentTime)}
                  className="order-first shrink-0 pb-1 text-caption text-muted opacity-0 transition-opacity duration-100 peer-hover:opacity-100"
                >
                  {sentTime}
                </time>
              ) : undefined}
            />
            <AssistantMessage>
              {isLast && isLiveLastTurn && liveAttachments.length > 0 && <UserAttachments files={liveAttachments} />}
              {running && turn.steps.length === 0 && (
                <div className="flex items-center gap-2 text-footnote text-muted">
                  <ActivityGlyph activity="think" />
                  <span className="text-shimmer font-medium">{t.chat.thinking}</span>
                </div>
              )}
              <AgentActivity
                steps={turn.steps}
                sources={turn.sources}
                variant={toolView}
                running={running}
                answering={turn.answer.length > 0}
                revising={Boolean(turn.staleAnswer)}
                expandedMap={expandedSteps}
                onToggleStep={onToggleStep}
              />
              {(turn.answer.length > 0 || turn.streaming) && (
                // 回答と根拠カード。幅が足りれば横に、足りなければ下に並べる（specs/025 R45）
                <div className="@container">
                  <div className="grid grid-cols-[minmax(0,1fr)] gap-x-6 gap-y-3.5 @[760px]:grid-cols-[minmax(0,1fr)_248px]">
                    {turn.streaming && turn.answer.length === 0 && turn.staleAnswer ? (
                      // 差し戻された下書き: 書き直しが届くまで薄く残す（急に消えて行が跳ねないように）
                      <div className="flex flex-col gap-2" aria-live="polite">
                        <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-accent-soft px-2 py-0.5 text-caption font-medium text-accent">
                          <span className="h-1.5 w-1.5 animate-breathe rounded-full bg-accent motion-reduce:animate-none" />
                          {t.chat.staleDraft}
                        </span>
                        <div className="pointer-events-none select-none opacity-40 transition-opacity duration-(--duration-mid)" aria-hidden>
                          <StreamingAnswer text={turn.staleAnswer} streaming={false} onCite={() => {}} citationStyle={citationStyle} />
                        </div>
                      </div>
                    ) : (
                      <StreamingAnswer text={turn.answer} streaming={turn.streaming} onCite={(n) => onCite(n, idx)} citationStyle={citationStyle} />
                    )}
                    <EvidenceRail items={evidenceList(turn.citationMap, turn.sources)} onOpen={(n) => onCite(n, idx)} />
                  </div>
                </div>
              )}
              {/* 取消でも途中までの回答は残す（runner が保存する） */}
              {turn.status === "cancelled" && <CancelledNotice onRetry={() => onRegenerate(idx)} />}
              {turn.status === "done" && turn.noAnswerReason === "no_relevant_sources" && turn.answer.trim() && (
                <UncitedNotice />
              )}
              {turn.status === "done" && <UnverifiedNumbersNotice numbers={unverifiedNumbers(turn.steps)} />}
              {turn.status === "error" && <ErrorNotice message={turn.error} onRetry={() => onRegenerate(idx)} />}
              {/* 各 done 回答が自分の指標・操作を持つ（複数ターン対応）。 */}
              {turn.status === "done" && (
                <AnswerFooter
                  tokens={turn.tokens} durationMs={turn.durationMs} sources={turn.sources}
                  onCopy={() => onCopy(idx)} onDownload={() => onDownload(idx)} onDownloadHtml={() => onDownloadHtml(idx)} onRegenerate={() => onRegenerate(idx)}
                  onOpenSources={() => onOpenSources(idx)}
                  sourcesActive={rightPanelOpen && activeCiteTurn === idx}
                  onFeedback={(v) => onFeedback(v, idx)}
                  onFeedbackDetail={(v) => onFeedbackDetail(v, idx)}
                  feedback={feedback[idx] ?? turn.feedback ?? null}
                  feedbackDisabled={!turn.messageId}
                />
              )}
              {onFollowup && <Followups items={followupsFor(turn, isLast, running)} onSend={onFollowup} />}
            </AssistantMessage>
          </div>
        );
      })}
    </>
  );
}
