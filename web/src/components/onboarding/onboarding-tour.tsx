"use client";

/** 初回ガイド（specs/015-help-onboarding R5）。旧版のスポットライトツアーの移植。
 *  半透明のマスクで `data-tour` の対象をくり抜いて示し、横のカードで順に説明する。
 *  対象が見えないステップ（375px で閉じたサイドバー等）は飛ばさず、スポットライト無しのカードにする。 */
import { m, type Variants } from "motion/react";
import { DURATION, EASE } from "@/lib/motion";
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  isVisibleRect,
  placePopover,
  spotlightRect,
  TOUR_STEPS,
  type Rect,
} from "@/lib/onboarding";
import { cn } from "@/lib/utils";

const POPOVER_WIDTH = 320;
const MOVE = "0.45s cubic-bezier(0.3, 0.7, 0.4, 1)";
/** 開くとき、スポットライトをこの分だけ広げた形から対象へ絞り込む */
const IRIS = 36;

/** カードの中身は段ごとに入れ替え、進む向きへ少しずらしながら上から順に現す */
const CONTENT: Variants = {
  enter: { transition: { staggerChildren: 0.045, delayChildren: 0.06 } },
};
const LINE: Variants = {
  from: (dir: number) => ({ opacity: 0, x: dir * 10, filter: "blur(3px)" }),
  enter: {
    opacity: 1,
    x: 0,
    filter: "blur(0px)",
    transition: { duration: DURATION.slow, ease: EASE.out },
  },
};

function inflate(r: Rect, d: number): Rect {
  return {
    left: r.left - d,
    top: r.top - d,
    width: r.width + d * 2,
    height: r.height + d * 2,
  };
}

interface Layout {
  target: Rect | null;
  viewport: { width: number; height: number };
}

function measure(id: string): Layout {
  const viewport = { width: window.innerWidth, height: window.innerHeight };
  const r = document
    .querySelector(`[data-tour="${id}"]`)
    ?.getBoundingClientRect();
  const rect = r
    ? { left: r.left, top: r.top, width: r.width, height: r.height }
    : null;
  return { target: isVisibleRect(rect, viewport) ? rect : null, viewport };
}

export function OnboardingTour({
  name,
  onClose,
}: {
  name?: string;
  onClose: () => void;
}) {
  const maskId = useId();
  const popoverRef = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);
  const [dir, setDir] = useState(1);
  const [opened, setOpened] = useState(false);
  const [layout, setLayout] = useState<Layout | null>(null);
  const [popH, setPopH] = useState(170);
  const step = TOUR_STEPS[index];
  const last = index === TOUR_STEPS.length - 1;

  // 対象の位置を測り、リサイズ・スクロールに追従する
  useLayoutEffect(() => {
    const update = () => setLayout(measure(step.id));
    const find = () => document.querySelector(`[data-tour="${step.id}"]`);
    // 一覧の読み込みなどで対象の大きさが後から変わっても追従する
    const ro = new ResizeObserver(update);
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    // 画面を移った直後は対象がまだ描かれていないことがあるので、数フレーム待ってから測る
    let tries = 0;
    let raf = 0;
    const watch = () => {
      const el = find();
      if (el) {
        ro.observe(el);
        update();
      } else if (++tries <= 30) raf = requestAnimationFrame(watch);
    };
    watch();
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
      ro.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [step.id]);

  // カードの実寸で配置を補正する
  useLayoutEffect(() => {
    const h = popoverRef.current?.offsetHeight;
    if (h && h !== popH) setPopH(h);
  }, [index, layout, popH]);

  // 最初の 1 枚を描いてから絞り込む（広げた形を一度描かないと transition が効かない）
  useEffect(() => {
    if (!layout || opened) return;
    let b = 0;
    const a = requestAnimationFrame(
      () => (b = requestAnimationFrame(() => setOpened(true))),
    );
    return () => {
      cancelAnimationFrame(a);
      cancelAnimationFrame(b);
    };
  }, [layout, opened]);

  const go = (next: number) => {
    const n = Math.max(0, Math.min(next, TOUR_STEPS.length - 1));
    setDir(n >= index ? 1 : -1);
    setIndex(n);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight")
        setIndex((i) => {
          setDir(1);
          return Math.min(i + 1, TOUR_STEPS.length - 1);
        });
      else if (e.key === "ArrowLeft")
        setIndex((i) => {
          setDir(-1);
          return Math.max(i - 1, 0);
        });
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!layout) return null;
  const { target, viewport } = layout;
  const width = Math.min(POPOVER_WIDTH, viewport.width - 32);
  const spot = target ? spotlightRect(target) : null;
  const pos = spot
    ? placePopover(spot, { width, height: popH }, viewport)
    : null;
  // 描く形（開く前は広げておき、opened で対象へ絞り込む）
  const shape = spot && !opened ? inflate(spot, IRIS) : spot;
  const moveRect = {
    transition: `x ${MOVE}, y ${MOVE}, width ${MOVE}, height ${MOVE}, opacity ${MOVE}`,
  };
  const mobile = viewport.width < 768;

  const card = (
    <>
      <m.div
        key={index}
        custom={dir}
        variants={CONTENT}
        initial="from"
        animate="enter"
      >
        <m.div
          variants={LINE}
          custom={dir}
          className="mb-1 flex items-center justify-between gap-2"
        >
          <span className="font-mono text-mini font-bold tracking-[0.08em] text-accent">
            {index + 1} / {TOUR_STEPS.length}
          </span>
          {index === 0 && name && (
            <span className="truncate text-caption text-muted">
              {name} さん、ようこそ
            </span>
          )}
        </m.div>
        <m.div
          variants={LINE}
          custom={dir}
          id="tour-title"
          className="text-callout font-bold tracking-[-0.01em] text-fg"
        >
          {step.title}
        </m.div>
        <m.p
          variants={LINE}
          custom={dir}
          className="m-0 mt-1.5 text-body leading-[1.6] text-muted"
        >
          {step.body}
        </m.p>
      </m.div>
      <div className="mt-3.5 flex items-center justify-between gap-3">
        <div className="flex items-center gap-1.5" aria-hidden>
          {TOUR_STEPS.map((s, i) => (
            <span
              key={s.id}
              className={cn(
                "h-1.5 rounded-full transition-[width,background-color] duration-(--duration-slow) ease-(--ease-out)",
                i === index
                  ? "w-4 bg-accent"
                  : i < index
                    ? "w-1.5 bg-accent/40"
                    : "w-1.5 bg-divider-strong",
              )}
            />
          ))}
        </div>
        <div className="flex items-center gap-1.5">
          {index === 0 ? (
            <Button
              variant="ghost"
              size="sm"
              className="text-muted hover:text-fg"
              onClick={onClose}
            >
              スキップ
            </Button>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              className="text-muted hover:text-fg"
              onClick={() => go(index - 1)}
            >
              戻る
            </Button>
          )}
          <Button
            variant="primary"
            size="sm"
            autoFocus
            onClick={() => (last ? onClose() : go(index + 1))}
          >
            {last ? "はじめる" : "次へ"}
          </Button>
        </div>
      </div>
    </>
  );

  const cardCls =
    "animate-dialog-in overflow-hidden rounded-sheet border-[0.5px] border-divider-strong bg-surface p-4 shadow-[0_20px_60px_rgba(0,0,0,0.3)] motion-reduce:animate-none";

  return (
    <m.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{
        opacity: 0,
        transition: { duration: DURATION.exit, ease: EASE.in },
      }}
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
            {shape && (
              <rect
                x={shape.left}
                y={shape.top}
                width={shape.width}
                height={shape.height}
                rx="12"
                fill="black"
                className="motion-reduce:[transition:none]"
                style={moveRect}
              />
            )}
          </mask>
        </defs>
        <rect
          width="100%"
          height="100%"
          fill="rgba(20,18,15,0.55)"
          mask={`url(#${maskId})`}
        />
      </svg>
      {shape && (
        <div
          aria-hidden
          className="pointer-events-none absolute rounded-[12px] border-[1.5px] border-accent shadow-[0_0_0_4px_var(--accent-glow),0_0_24px_var(--accent-glow)] motion-reduce:[transition:none]"
          style={{
            left: shape.left,
            top: shape.top,
            width: shape.width,
            height: shape.height,
            opacity: opened ? 1 : 0,
            transition: `left ${MOVE}, top ${MOVE}, width ${MOVE}, height ${MOVE}, opacity ${MOVE}`,
          }}
        >
          {/* 対象に着くたびに 1 度だけ外へ広がる輪 */}
          {opened && (
            <span
              key={index}
              className="absolute -inset-[1.5px] rounded-[12px] animate-tour-ping motion-reduce:hidden"
            />
          )}
        </div>
      )}
      {pos ? (
        <div
          ref={popoverRef}
          className={cn("absolute motion-reduce:[transition:none]", cardCls)}
          style={{
            width,
            top: pos.top,
            left: pos.left,
            transition: `top ${MOVE}, left ${MOVE}`,
          }}
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
