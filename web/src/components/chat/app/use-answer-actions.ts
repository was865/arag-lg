"use client";

/** 回答への操作（コピー・Markdown / HTML で書き出す・評価を送る）。 */
import { isUnsavedMessage } from "@/components/chat/answer-footer";
import { useToast } from "@/components/feedback/toast-provider";
import { useT } from "@/i18n/context";
import { chatApi } from "@/lib/chat/api";
import { answerHtml, answerMarkdown, exportFileBase } from "@/lib/chat/export";
import type { FeedbackRating, FeedbackReasonTag, TurnFeedback } from "@/lib/feedback-types";
import type { Turn } from "@/lib/types";

function saveFile(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export function useAnswerActions({
  turns,
  threadId,
  setFeedback,
  markUnsaved,
}: {
  turns: Turn[];
  threadId: string | null;
  setFeedback: (threadId: string, idx: number, fb: TurnFeedback | null) => void;
  markUnsaved: (threadId: string, idx: number) => void;
}) {
  const { t } = useT();
  const push = useToast();

  const copy = async (idx: number) => {
    try {
      const text = (turns[idx]?.answer ?? "").replace(/\*\*/g, "").replace(/\[\d+\]/g, "");
      await navigator.clipboard.writeText(text);
      push(t.feedback.answerCopied, "success");
    } catch {
      push(t.feedback.copyFailed, "error");
    }
  };

  // 質問・回答・出典の一覧をまとめて書き出す（lib/chat/export）
  const download = (idx: number) => {
    const turn = turns[idx];
    if (!turn?.answer) return;
    saveFile(`${exportFileBase(turn.query)}.md`, answerMarkdown(turn), "text/markdown;charset=utf-8");
  };

  const downloadHtml = async (idx: number) => {
    const turn = turns[idx];
    if (!turn?.answer) return;
    try {
      const { renderMarkdown } = await import("@/lib/chat/export-render");
      saveFile(`${exportFileBase(turn.query)}.html`, answerHtml(turn, renderMarkdown), "text/html;charset=utf-8");
    } catch {
      push(t.chat.exportFailed, "error");
    }
  };

  const applyFeedback = async (idx: number, fb: TurnFeedback) => {
    const turn = turns[idx];
    if (!threadId || !turn?.messageId) return;
    const prev = turn.feedback ?? null;
    setFeedback(threadId, idx, fb);
    try {
      await chatApi.feedback(turn.messageId, { rating: fb.rating, reason_tags: fb.reasonTags, comment: fb.comment });
      push(fb.rating === "down" ? t.feedback.feedbackImprovement : t.feedback.feedbackSent, "success");
    } catch (e) {
      setFeedback(threadId, idx, prev);
      if (isUnsavedMessage(e)) {
        markUnsaved(threadId, idx);
        push(t.feedback.feedbackUnsaved, "error");
      } else push(t.feedback.feedbackFailed, "error");
    }
  };

  const onFeedback = (v: FeedbackRating, idx: number) => {
    if (v === "up") void applyFeedback(idx, { rating: "up", reasonTags: [], comment: null });
  };
  const onFeedbackDetail = (v: { reasonTags: FeedbackReasonTag[]; comment: string }, idx: number) => {
    void applyFeedback(idx, { rating: "down", reasonTags: v.reasonTags, comment: v.comment.trim() || null });
  };

  return { copy, download, downloadHtml, onFeedback, onFeedbackDetail };
}
