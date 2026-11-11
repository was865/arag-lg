"use client";

import { useCallback, useRef, useState } from "react";
import { uid } from "@/lib/utils";
import type { Toast, ToastKind } from "@/lib/types";

/** 束を広げて読んでいる間（pause）は自動で消さず、離れたら（resume）残り時間から数え直す。 */
const RESUME_MIN_MS = 1200;

export function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  // id → 消す予定（timer が null の間は止まっている）
  const timers = useRef(new Map<string, { timer: ReturnType<typeof setTimeout> | null; until: number; left: number }>());
  const paused = useRef(false);

  const remove = useCallback((id: string) => {
    const t = timers.current.get(id);
    if (t?.timer) clearTimeout(t.timer);
    timers.current.delete(id);
    // 最後の 1 枚を閉じると束が消えて「離れた」合図が来ないので、ここで止めた状態を解く
    if (timers.current.size === 0) paused.current = false;
    setToasts((prev) => prev.filter((x) => x.id !== id));
  }, []);

  const arm = useCallback(
    (id: string, ms: number) => {
      timers.current.set(id, { timer: setTimeout(() => remove(id), ms), until: Date.now() + ms, left: ms });
    },
    [remove],
  );

  const push = useCallback(
    (msg: string, kind: ToastKind = "info", ms = 2400) => {
      const id = uid();
      setToasts((prev) => [...prev, { id, msg, kind }]);
      if (paused.current) timers.current.set(id, { timer: null, until: 0, left: ms });
      else arm(id, ms);
    },
    [arm],
  );

  const pause = useCallback(() => {
    if (paused.current) return;
    paused.current = true;
    for (const t of timers.current.values()) {
      if (t.timer) clearTimeout(t.timer);
      t.left = Math.max(0, t.until - Date.now());
      t.timer = null;
    }
  }, []);

  const resume = useCallback(() => {
    if (!paused.current) return;
    paused.current = false;
    for (const [id, t] of [...timers.current]) arm(id, Math.max(RESUME_MIN_MS, t.left));
  }, [arm]);

  return { toasts, push, dismiss: remove, pause, resume };
}

export type PushToast = ReturnType<typeof useToasts>["push"];
