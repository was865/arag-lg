"use client";

import { useState } from "react";
import { AnimatePresence, m } from "motion/react";
import { createPortal } from "react-dom";
import { Button, ICON, IconButton } from "@/components/ui/button";
import { AnswerMarkdown } from "@/components/chat/answer-markdown";
import { AgentActivity } from "@/components/chat/agent-activity";
import { EvidenceRail } from "@/components/chat/evidence-rail";
import { evidenceList } from "@/lib/chat/evidence";
import { ActivityGlyph } from "@/components/chat/activity-glyph";
import {
  AnswerFooter,
  CancelledNotice,
  ErrorNotice,
  ReportProblem,
  canReport,
  UncitedNotice,
  UnverifiedNumbersNotice,
  unverifiedNumbers,
} from "@/components/chat/answer-footer";
import { UserAttachments } from "@/components/uploads/uploads";
import type { CitationStyle, StagedFile, Turn, TurnImage, ToolView } from "@/lib/types";
import type { FeedbackReasonTag, TurnFeedback } from "@/lib/feedback-types";
import { useT } from "@/i18n/context";
import { useToast } from "@/components/feedback/toast-provider";
import { Icon } from "@/components/icons";
import { DURATION, EASE } from "@/lib/motion";
import { cn } from "@/lib/utils";
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
      {/* 会話の列の中に置くと、上の見出しや入力欄（それぞれ重なりの層を持つ）の下に潜るので、body 直下に出す */}
      {open &&
        createPortal(
          <div
            role="dialog"
            // eslint-disable-next-line no-restricted-syntax -- 画像の拡大表示（ライトボックス）。枠のない全面表示で、Esc は自前で処理する
            aria-modal="true"
            aria-label={t.chat.imageAttached}
            onClick={() => setOpen(false)}
            onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
            tabIndex={-1}
            ref={(el) => el?.focus()}
            className="fixed inset-0 z-[230] grid place-items-center bg-[rgba(20,18,15,0.72)] p-4 outline-none"
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- 拡大表示 */}
            <img
              src={image.url}
              alt={t.chat.imageAttached}
              className="block max-h-[calc(100dvh-2rem)] max-w-[calc(100vw-2rem)] rounded-card object-contain"
            />
          </div>,
          document.body,
        )}
    </>
  );
}

/** 質問の下に並べる小さな操作（時刻・コピー・編集）。ホバーかフォーカスで、少し下りながら出す。触る端末では常に出す。 */
const questionActionsClass =
  "flex h-6 items-center gap-0.5 -translate-y-0.5 opacity-0 transition-[opacity,translate] duration-(--duration-mid) ease-(--ease-out) group-hover/q:translate-y-0 group-hover/q:opacity-100 group-focus-within/q:translate-y-0 group-focus-within/q:opacity-100 [@media(hover:none)]:translate-y-0 [@media(hover:none)]:opacity-100";

/** 吹き出しの角。Motion の layout は style で渡した角丸だけを伸び縮みの間も補正する */
const BUBBLE_RADIUS = { borderTopLeftRadius: 16, borderTopRightRadius: 16, borderBottomLeftRadius: 16, borderBottomRightRadius: 4 };

/** 中身の差し替え。箱が形を変えるあいだ、少し遅れて淡く出す */
const contentIn = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: DURATION.mid, ease: EASE.out, delay: 0.05 } },
} as const;

export function UserMessage({
  text,
  sentAt,
  onEdit,
  onEditingChange,
  laterTurns = 0,
  image,
}: {
  text: string;
  /** 質問に添えた画像（specs/017） */
  image?: TurnImage;
  /** 送った時刻（ISO）。質問の下の操作の列に時刻だけを出し、ツールチップで日付まで出す */
  sentAt?: string;
  /** 指定すると「編集」を出し、送信でこのターンから作り直す（R34）。 */
  onEdit?: (text: string) => void;
  /** 編集を開いた・閉じたとき。作り直しで置き換わる回答を淡くするのに使う */
  onEditingChange?: (editing: boolean) => void;
  /** このターンより後のターンの数。編集で消えるものを先に伝える */
  laterTurns?: number;
}) {
  const { t } = useT();
  const push = useToast();
  const [editing, setEditingState] = useState(false);
  const [draft, setDraft] = useState(text);
  const [copied, setCopied] = useState(false);
  const time = sentAt ? formatTurnTimestamp(sentAt) : "";
  const isEditing = editing && !!onEdit;

  const setEditing = (v: boolean) => {
    setEditingState(v);
    onEditingChange?.(v);
  };

  // 押した場所でチェックに変えて知らせる（トーストは出さない）
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      push(t.feedback.copyFailed, "error");
    }
  };

  // 文が同じでも送る（その質問で作り直す）。何も起きずに閉じると、送れたのか分からない
  const submit = () => {
    const v = draft.trim();
    if (!v || !onEdit) return;
    setEditing(false);
    onEdit(v);
  };
  const cancel = () => {
    setEditing(false);
    setDraft(text);
  };

  return (
    <div className="group/q flex flex-col items-end gap-1">
      {/* 吹き出しと編集欄は同じ箱。開閉で箱が形と色を変え、中身は少し遅れて出る */}
      <m.div
        layout
        layoutDependency={isEditing}
        style={BUBBLE_RADIUS}
        className={cn(
          "max-w-[80%] overflow-hidden border-[0.5px] transition-[background-color,border-color,box-shadow] duration-(--duration-mid) ease-(--ease-out)",
          isEditing
            ? "w-full border-divider-strong bg-surface p-2.5 shadow-e1 focus-within:ring-2 focus-within:ring-accent/30 max-md:max-w-[92%]"
            : "border-transparent bg-bubble-user px-4 py-3 max-md:max-w-[88%] max-md:px-3.5 max-md:py-[11px]",
        )}
      >
        {isEditing ? (
          <m.div key="edit" layout="position" layoutDependency={isEditing} {...contentIn}>
            <textarea
              // 開いたらカーソルを末尾に置く（足して直すことが多い）
              ref={(el) => {
                if (el && document.activeElement !== el) {
                  el.focus({ preventScroll: true });
                  el.setSelectionRange(el.value.length, el.value.length);
                }
              }}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  submit();
                } else if (e.key === "Escape") {
                  e.preventDefault();
                  cancel();
                }
              }}
              rows={1}
              aria-label={t.chat.editQuestion}
              className="max-h-[40vh] min-h-[1.55em] w-full resize-none border-0 bg-transparent px-1.5 py-1 text-callout leading-[1.55] text-fg outline-none [field-sizing:content]"
            />
            <div className="mt-1.5 flex items-center gap-2">
              <span className="min-w-0 flex-1 text-caption text-muted">
                {laterTurns > 0
                  ? t.chat.editHintBranch.replace("{n}", String(laterTurns))
                  : t.chat.editHintLast}
              </span>
              <Button variant="secondary" size="sm" onClick={cancel}>{t.chat.editCancel}</Button>
              <Button variant="primary" size="sm" type="button" onClick={submit} disabled={!draft.trim()}>
                {t.chat.editSubmit}
              </Button>
            </div>
          </m.div>
        ) : (
          <m.div
            key="view"
            layout="position"
            layoutDependency={isEditing}
            {...contentIn}
            className="whitespace-pre-wrap text-callout leading-[1.55] text-bubble-user-fg [overflow-wrap:anywhere]"
          >
            {image && (
              <div className="mb-2">
                <QueryImageThumb image={image} />
              </div>
            )}
            {text}
          </m.div>
        )}
      </m.div>
      {!isEditing && (
        <div className={questionActionsClass}>
          {time && (
            <time
              dateTime={sentAt}
              title={new Date(sentAt!).toLocaleString("ja-JP")}
              aria-label={t.chat.sentAt.replace("{time}", time)}
              className="px-1.5 text-caption tabular-nums text-muted"
            >
              {time}
            </time>
          )}
          <IconButton
            label={copied ? t.chat.copied : t.chat.copyQuestion}
            size="icon-sm"
            onClick={() => void copy()}
            className={cn(copied && "text-fg")}
          >
            <span className="grid place-items-center">
              <AnimatePresence initial={false} mode="popLayout">
                <m.span
                  key={copied ? "done" : "copy"}
                  className="col-start-1 row-start-1 grid place-items-center"
                  initial={{ opacity: 0, scale: 0.5 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.5, transition: { duration: DURATION.exit } }}
                >
                  <Icon name={copied ? "check" : "copy"} size={ICON.sm} />
                </m.span>
              </AnimatePresence>
            </span>
          </IconButton>
          {onEdit && (
            <IconButton
              label={t.chat.editQuestion}
              icon="pencil"
              size="icon-sm"
              iconSize={ICON.sm}
              onClick={() => {
                setDraft(text);
                setEditing(true);
              }}
            />
          )}
        </div>
      )}
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
export function AssistantMessage({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("flex min-w-0 flex-col gap-3.5 max-md:gap-3", className)}>{children}</div>;
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
  onCopy, onDownload, onDownloadHtml, onRegenerate, onFeedback, onFeedbackDetail, feedback,
  liveAttachments, isLiveLastTurn, onEdit, onFollowup,
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
  onFeedback: (v: "up" | "down", turnIdx: number) => void;
  onFeedbackDetail: (v: { reasonTags: FeedbackReasonTag[]; comment: string }, turnIdx: number) => void;
  // 楽観的更新用の上書き（未設定なら turn.feedback にフォールバック）。
  feedback: Record<number, TurnFeedback | null>;
  liveAttachments: StagedFile[];
  isLiveLastTurn: boolean;
  /** 質問の編集→作り直し。未指定なら編集 UI を出さない（生成中など）。 */
  onEdit?: (turnIdx: number, text: string) => void;
  /** 続けて聞く候補を押したとき（specs/028）。未指定（生成中など）なら候補を出さない。 */
  onFollowup?: (text: string) => void;
}) {
  const { t } = useT();
  const now = new Date();
  // 編集中のターン。その回答と後のターンは作り直しで置き換わるので淡くして先に見せる
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const dim = (idx: number, from: "this" | "later") =>
    onEdit != null && editingIdx != null && (from === "this" ? idx === editingIdx : idx > editingIdx);
  const fade = "transition-opacity duration-(--duration-slow) ease-(--ease-out)";
  // 保存したメッセージがあるときだけ（受付前の取消・runner_lost の失敗では出さない）
  const report = (turn: Turn, idx: number) =>
    canReport(turn) ? <ReportProblem onSubmit={(v) => onFeedbackDetail(v, idx)} /> : undefined;
  return (
    <>
      {turns.map((turn, idx) => {
        const isLast = idx === turns.length - 1;
        const running = turn.status === "running";
        // 先頭、または前ターンと暦日が変わったら日付セパレータを挿入。
        const prev = turns[idx - 1];
        const showSeparator = !!turn.createdAt &&
          (idx === 0 || !prev?.createdAt || !sameLocalDay(new Date(prev.createdAt), new Date(turn.createdAt)));
        return (
          <div key={idx} data-turn={idx} className={cn("flex flex-col gap-6 max-md:gap-[18px]", fade, dim(idx, "later") && "opacity-35")}>
            {showSeparator && <DateSeparator label={dateSeparator(turn.createdAt!, now, { today: t.chat.dateToday, yesterday: t.chat.dateYesterday })} />}
            <UserMessage
              text={turn.query}
              image={turn.image}
              sentAt={turn.createdAt}
              laterTurns={turns.length - 1 - idx}
              onEdit={onEdit && turn.messageId && !running ? (v) => { setEditingIdx(null); onEdit(idx, v); } : undefined}
              onEditingChange={(v) => setEditingIdx((cur) => (v ? idx : cur === idx ? null : cur))}
            />
            <AssistantMessage className={cn(fade, dim(idx, "this") && "opacity-35")}>
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
              {turn.status === "cancelled" && <CancelledNotice onRetry={() => onRegenerate(idx)} report={report(turn, idx)} />}
              {turn.status === "done" && turn.noAnswerReason === "no_relevant_sources" && turn.answer.trim() && (
                <UncitedNotice />
              )}
              {turn.status === "done" && <UnverifiedNumbersNotice numbers={unverifiedNumbers(turn.steps)} />}
              {turn.status === "error" && <ErrorNotice message={turn.error} onRetry={() => onRegenerate(idx)} report={report(turn, idx)} />}
              {/* 回答なし（資料が無い・上限など）も「問題を報告」から過程ごと届ける（specs/028 R12） */}
              {turn.status === "done" && turn.noAnswerReason && canReport(turn) && (
                <div className="-mb-1 flex">{report(turn, idx)}</div>
              )}
              {/* 各 done 回答が自分の指標・操作を持つ（複数ターン対応）。 */}
              {turn.status === "done" && (
                <AnswerFooter
                  tokens={turn.tokens} durationMs={turn.durationMs}
                  onCopy={() => onCopy(idx)} onDownload={() => onDownload(idx)} onDownloadHtml={() => onDownloadHtml(idx)} onRegenerate={() => onRegenerate(idx)}
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
