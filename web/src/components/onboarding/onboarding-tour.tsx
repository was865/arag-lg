"use client";

/** 初回ガイド（specs/015-help-onboarding R5）。旧版のスポットライトツアーの移植。
 *  半透明のマスクで `data-tour` の対象をくり抜いて示し、横のカードで順に説明する。
 *  対象が見えないステップ（375px で閉じたサイドバー等）は飛ばさず、スポットライト無しのカードにする。 */
import { m } from "motion/react";
import { DURATION, EASE } from "@/lib/motion";
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { isVisibleRect, placePopover, spotlightRect, TOUR_STEPS, type Rect } from "@/lib/onboarding";
import { cn } from "@/lib/utils";

const POPOVER_WIDTH = 320;
const MOVE = "0.4s cubic-bezier(0.3, 0.7, 0.4, 1)";

interface Layout {
  target: Rect | null;
  viewport: { width: number; height: number };
}

function measure(id: string): Layout {
  const viewport = { width: window.innerWidth, height: window.innerHeight };
  const r = document.querySelector(`[data-tour="${id}"]`)?.getBoundingClientRect();
  const rect = r ? { left: r.left, top: r.top, width: r.width, height: r.height } : null;
  return { target: isVisibleRect(rect, viewport) ? rect : null, viewport };
}

export function OnboardingTour({ name, onClose }: { name?: string; onClose: () => void }) {
  const maskId = useId();
  const popoverRef = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);
  const [layout, setLayout] = useState<Layout | null>(null);
  const [popH, setPopH] = useState(170);
  const step = TOUR_STEPS[index];
  const last = index === TOUR_STEPS.length - 1;

  // 対象の位置を測り、リサイズ・スクロールに追従する
  useLayoutEffect(() => {
    const update = () => setLayout(measure(step.id));
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    // 一覧の読み込みなどで対象の大きさが後から変わっても追従する
    const el = document.querySelector(`[data-tour="${step.id}"]`);
    const ro = el ? new ResizeObserver(update) : null;
    if (el) ro?.observe(el);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
      ro?.disconnect();
    };
  }, [step.id]);

  // カードの実寸で配置を補正する
  useLayoutEffect(() => {
    const h = popoverRef.current?.offsetHeight;
    if (h && h !== popH) setPopH(h);
  }, [index, layout, popH]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight") setIndex((i) => Math.min(i + 1, TOUR_STEPS.length - 1));
      else if (e.key === "ArrowLeft") setIndex((i) => Math.max(i - 1, 0));
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!layout) return null;
  const { target, viewport } = layout;
  const width = Math.min(POPOVER_WIDTH, viewport.width - 32);
  const spot = target ? spotlightRect(target) : null;
  const pos = spot ? placePopover(spot, { width, height: popH }, viewport) : null;
  const mobile = viewport.width < 768;

  const card = (
    <>
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="font-mono text-mini font-bold tracking-[0.08em] text-accent">
          {index + 1} / {TOUR_STEPS.length}
        </span>
        {index === 0 && name && <span className="truncate text-caption text-muted">{name} さん、ようこそ</span>}
      </div>
      <div id="tour-title" className="text-callout font-bold tracking-[-0.01em] text-fg">
        {step.title}
      </div>
      <p className="m-0 mt-1.5 text-body leading-[1.6] text-muted">{step.body}</p>
      <div className="mt-3.5 flex items-center justify-between gap-3">
        <div className="flex items-center gap-1.5" aria-hidden>
          {TOUR_STEPS.map((s, i) => (
            <span
              key={s.id}
              className={cn("h-1.5 rounded-full transition-all", i === index ? "w-4 bg-accent" : "w-1.5 bg-divider-strong")}
            />
          ))}
        </div>
        <div className="flex items-center gap-1.5">
          {index === 0 ? (
            <Button variant="ghost" size="sm" className="text-muted hover:text-fg"
              onClick={onClose}
            >
              スキップ
            </Button>
          ) : (
            <Button variant="ghost" size="sm" className="text-muted hover:text-fg"
              onClick={() => setIndex(index - 1)}
            >
              戻る
            </Button>
          )}
          <Button variant="primary" size="sm"
            autoFocus
            onClick={() => (last ? onClose() : setIndex(index + 1))}
          >
            {last ? "はじめる" : "次へ"}
          </Button>
        </div>
      </div>
    </>
  );

  const cardCls =
    "animate-pop-in rounded-sheet border-[0.5px] border-divider-strong bg-surface p-4 shadow-[0_20px_60px_rgba(0,0,0,0.3)] motion-reduce:animate-none";

  return (
    <m.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: DURATION.exit, ease: EASE.in } }}
      className="fixed inset-0 z-[240]"
      role="dialog"
      // eslint-disable-next-line no-restricted-syntax -- 画面の一部を切り抜いて強調するツアー。暗転の形が特殊なため自前で描く
      aria-modal="true"
      aria-labelledby="tour-title"
    >
      <svg className="absolute inset-0 h-full w-full" aria-hidden="true">
        <defs>
          <mask id={maskId}>
            <rect width="100%" height="100%" fill="white" />
            {spot && (
              <rect
                x={spot.left}
                y={spot.top}
                width={spot.width}
                height={spot.height}
                rx="12"
                fill="black"
                className="motion-reduce:[transition:none]"
                style={{ transition: `x ${MOVE}, y ${MOVE}, width ${MOVE}, height ${MOVE}` }}
              />
            )}
          </mask>
        </defs>
        <rect width="100%" height="100%" fill="rgba(20,18,15,0.55)" mask={`url(#${maskId})`} />
        {spot && (
          <rect
            x={spot.left}
            y={spot.top}
            width={spot.width}
            height={spot.height}
            rx="12"
            fill="none"
            stroke="var(--accent)"
            strokeWidth="1.5"
            className="motion-reduce:[transition:none]"
            style={{ transition: `x ${MOVE}, y ${MOVE}, width ${MOVE}, height ${MOVE}` }}
          />
        )}
      </svg>
      {pos ? (
        <div
          ref={popoverRef}
          className={cn("absolute motion-reduce:[transition:none]", cardCls)}
          style={{ width, top: pos.top, left: pos.left, transition: `top ${MOVE}, left ${MOVE}` }}
        >
          {card}
        </div>
      ) : mobile ? (
        <div
          ref={popoverRef}
          className={cn(
            "absolute inset-x-0 bottom-0 rounded-b-none pb-[max(16px,env(safe-area-inset-bottom))]",
            cardCls,
          )}
        >
          {card}
        </div>
      ) : (
        <div className="absolute inset-0 grid place-items-center p-6">
          <div ref={popoverRef} className={cardCls} style={{ width }}>
            {card}
          </div>
        </div>
      )}
    </m.div>
  );
}
