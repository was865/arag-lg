"use client";

/** スレッドごとの会話と、生成中の run のストリーム（specs/005-agent D3・D6、R35）。
 *
 * - run は API 側で動き続けるので、スレッドを切り替えても購読は止めない（戻れば続きが見える）。
 * - 再読み込み後は thread の active_run から購読し直す（ストリームは先頭から再生される）。
 * - 切断時は EventSource が Last-Event-ID 付きで自動再接続する。期限切れ（410）なら保存済みを読み直す。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, chatApi, streamUrl, type StartRunBody } from "@/lib/chat/api";
import { applyEvent, isTerminal, newTurn, turnFromMessage, type RunEvent } from "@/lib/chat/turn";
import type { Turn } from "@/lib/types";
import { uid } from "@/lib/utils";

export const NEW_THREAD = "new";

export const RUN_EVENT_TYPES: RunEvent["type"][] = [
  "run.started",
  "step",
  "answer.delta",
  "answer.reset",
  "sources",
  "run.completed",
  "run.failed",
  "run.cancelled",
];

export interface Conversation {
  turns: Turn[];
  loaded: boolean;
  /** 再接続中（EventSource が繋ぎ直している）。 */
  reconnecting?: boolean;
}

interface Options {
  /** run が終わった（完了・失敗・取消）。スレッド一覧の並び替えなどに使う。 */
  onRunEnd?: (threadId: string) => void;
  /** 新しいスレッドができた（最初の質問の送信後）。 */
  onThreadCreated?: (threadId: string) => void;
}

export function useConversations({ onRunEnd, onThreadCreated }: Options = {}) {
  const [convs, setConvs] = useState<Record<string, Conversation>>({});
  const streams = useRef(new Map<string, EventSource>());
  const cbs = useRef({ onRunEnd, onThreadCreated });
  useEffect(() => {
    cbs.current = { onRunEnd, onThreadCreated };
  });

  const update = useCallback((threadId: string, fn: (c: Conversation) => Conversation) => {
    setConvs((all) => ({ ...all, [threadId]: fn(all[threadId] ?? { turns: [], loaded: false }) }));
  }, []);

  const patchRun = useCallback(
    (threadId: string, runId: string, fn: (t: Turn) => Turn) =>
      update(threadId, (c) => ({ ...c, turns: c.turns.map((t) => (t.runId === runId ? fn(t) : t)) })),
    [update],
  );

  // follow ⇄ load は互いを呼ぶので、follow からは ref 経由で load を呼ぶ
  const loadRef = useRef<(threadId: string) => Promise<unknown>>(async () => undefined);

  const follow = useCallback(
    (threadId: string, runId: string) => {
      if (streams.current.has(runId)) return;
      const es = new EventSource(streamUrl(runId));
      streams.current.set(runId, es);
      const close = () => {
        es.close();
        streams.current.delete(runId);
      };
      const onEvent = (e: MessageEvent<string>) => {
        let ev: RunEvent;
        try {
          ev = JSON.parse(e.data) as RunEvent;
        } catch {
          return;
        }
        update(threadId, (c) => ({
          ...c,
          reconnecting: false,
          turns: c.turns.map((t) => (t.runId === runId ? applyEvent(t, ev) : t)),
        }));
        if (isTerminal(ev)) {
          close();
          cbs.current.onRunEnd?.(threadId);
        }
      };
      for (const type of RUN_EVENT_TYPES) es.addEventListener(type, onEvent as EventListener);
      es.onerror = () => {
        if (es.readyState === EventSource.CLOSED) {
          // 410（期限切れ）・404 など。保存済みの内容で置き換える
          close();
          void loadRef.current(threadId).catch(() => {
            patchRun(threadId, runId, (t) => ({ ...t, streaming: false, status: "error" }));
          });
        } else {
          update(threadId, (c) => ({ ...c, reconnecting: true }));
        }
      };
    },
    [update, patchRun],
  );

  const load = useCallback(
    async (threadId: string) => {
      const detail = await chatApi.thread(threadId);
      const turns = detail.messages.map(turnFromMessage);
      const active = detail.active_run;
      if (active) turns.push(newTurn(active.query, { runId: active.run_id, messageId: active.message_id }));
      update(threadId, () => ({ turns, loaded: true }));
      if (active) follow(threadId, active.run_id);
      return detail;
    },
    [update, follow],
  );
  useEffect(() => {
    loadRef.current = load;
  }, [load]);

  /** 質問を送る。fromIdx を渡すとそのターンから作り直す（再生成・質問の編集）。 */
  const send = useCallback(
    async (
      threadId: string | null,
      query: string,
      opts: { fromIdx?: number; fromMessageId?: string | null; body?: Partial<StartRunBody> } = {},
    ): Promise<string | null> => {
      const key = threadId ?? NEW_THREAD;
      const pending = `pending:${uid()}`;
      update(key, (c) => {
        const kept = opts.fromIdx != null ? c.turns.slice(0, opts.fromIdx) : c.turns;
        return { ...c, loaded: true, turns: [...kept, newTurn(query, { runId: pending })] };
      });
      try {
        const r = await chatApi.startRun(threadId, {
          include_archived: false,
          ...opts.body,
          query,
          from_message_id: opts.fromMessageId ?? null,
        });
        const realKey = r.thread_id;
        setConvs((all) => {
          const conv = all[key] ?? { turns: [], loaded: true };
          const turns = conv.turns.map((t) =>
            t.runId === pending ? { ...t, runId: r.run_id, messageId: r.message_id } : t,
          );
          const next = { ...all, [realKey]: { ...conv, turns } };
          if (key !== realKey) delete next[key];
          return next;
        });
        if (!threadId) cbs.current.onThreadCreated?.(realKey);
        follow(realKey, r.run_id);
        return realKey;
      } catch (e) {
        const message = e instanceof ApiError ? e.message : "送信に失敗しました。時間をおいてお試しください";
        patchRun(key, pending, (t) => ({ ...t, streaming: false, status: "error", error: message }));
        return null;
      }
    },
    [update, follow, patchRun],
  );

  const cancel = useCallback(async (runId: string) => {
    await chatApi.cancelRun(runId);
  }, []);

  const setFeedback = useCallback(
    (threadId: string, idx: number, feedback: Turn["feedback"]) =>
      update(threadId, (c) => ({ ...c, turns: c.turns.map((t, i) => (i === idx ? { ...t, feedback } : t)) })),
    [update],
  );

  const forget = useCallback((threadId: string) => {
    setConvs((all) => {
      const next = { ...all };
      delete next[threadId];
      return next;
    });
  }, []);

  useEffect(() => {
    const map = streams.current;
    return () => {
      for (const es of map.values()) es.close();
      map.clear();
    };
  }, []);

  return { convs, load, send, cancel, setFeedback, forget };
}
