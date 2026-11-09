"use client";

import { useEffect, useState } from "react";
import { chatApi, type ThreadSearchHit } from "@/lib/chat/api";

export type ThreadSearchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "done"; items: ThreadSearchHit[] }
  | { status: "error" };

const DEBOUNCE_MS = 250;

/** サイドバーの検索語でスレッドの本文まで探す（specs/022 R3）。入力が止まってから問い合わせ、古い問い合わせは中止する。 */
export function useThreadSearch(query: string): ThreadSearchState {
  const q = query.trim();
  // 結果はどの語の結果かと組で持つ。今の語と違えば「検索中」とみなす（effect の中で同期に setState しない）
  const [result, setResult] = useState<{ q: string; items: ThreadSearchHit[] | null } | null>(null);

  useEffect(() => {
    if (!q) return;
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      chatApi
        .searchThreads(q, ctrl.signal)
        .then((items) => setResult({ q, items }))
        .catch(() => {
          if (!ctrl.signal.aborted) setResult({ q, items: null });
        });
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [q]);

  if (!q) return { status: "idle" };
  if (!result || result.q !== q) return { status: "loading" };
  return result.items ? { status: "done", items: result.items } : { status: "error" };
}
