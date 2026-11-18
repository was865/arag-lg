"use client";

/** 初回ガイド（specs/015 R5）: ログインした利用者がこの端末でまだ見ていなければ、チャットで 1 回だけ出す。 */
import { useState, useSyncExternalStore } from "react";
import { guideKey, shouldShowGuide } from "@/lib/onboarding";

const noopSubscribe = () => () => {};

function readGuideSeen(userId: string | null): string | null {
  if (!userId) return "1";
  try {
    return localStorage.getItem(guideKey(userId));
  } catch {
    return "1";
  }
}

export function useGuide(userId: string | null, onChat: boolean) {
  const seen = useSyncExternalStore(
    noopSubscribe,
    () => readGuideSeen(userId),
    () => "1",
  );
  const [state, setState] = useState<"auto" | "open" | "closed">("auto");
  const open = state === "open" || (state === "auto" && onChat && shouldShowGuide({ userId, seen }));
  const close = () => {
    if (userId) {
      try {
        localStorage.setItem(guideKey(userId), "1");
      } catch {}
    }
    setState("closed");
  };
  return { open, close, replay: () => setState("open") };
}
