"use client";

/** 上へ送っているときに出す「最新へ」（生成中なら「生成中の回答へ」）。 */
import { AnimatePresence, m } from "motion/react";
import { DURATION } from "@/lib/motion";

export function JumpToLatest({ visible, running, onJump }: { visible: boolean; running: boolean; onJump: () => void }) {
  return (
    <AnimatePresence>
      {visible && (
        <m.div
          key="jump"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 8, transition: { duration: DURATION.exit } }}
          className="pointer-events-none relative h-0"
        >
          <button
            type="button"
            onClick={onJump}
            className="pointer-events-auto absolute -top-12 left-1/2 z-10 inline-flex h-8 -translate-x-1/2 items-center gap-1.5 rounded-full border-[0.5px] border-divider-strong bg-surface px-3 text-footnote font-medium text-fg shadow-e2 hover:bg-surface-2"
          >
            <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden>
              <path d="M8 3v10M8 13l-4-4M8 13l4-4" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {running ? "生成中の回答へ" : "最新へ"}
          </button>
        </m.div>
      )}
    </AnimatePresence>
  );
}
