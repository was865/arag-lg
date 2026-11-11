"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/icons";
import { useMediaQuery } from "@/hooks/use-media-query";
import type { UsageTip } from "@/lib/types";

/** 自動切替の間隔（ミリ秒）。 */
const ROTATE_MS = 5000;

interface TipCarouselProps {
  tips: UsageTip[];
  onFill: (text: string) => void;
}

/** zh 空状態の使い方ヒントを自動ローテーション表示する hero カード。
 *  カードクリックで onFill(tip.fill) を呼び、composer に例文を流し込む（送信はしない）。 */
export function TipCarousel({ tips, onFill }: TipCarouselProps) {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  // prefers-reduced-motion 指定時は自動切替しない（SSR-safe フック）。
  const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)");

  useEffect(() => {
    if (tips.length <= 1 || paused || reduceMotion) return;
    const id = window.setInterval(() => {
      setIndex((i) => (i + 1) % tips.length);
    }, ROTATE_MS);
    return () => window.clearInterval(id);
  }, [tips.length, paused, reduceMotion]);

  if (tips.length === 0) return null;
  // tips の件数が減ったケースに備えてクランプする。
  const tip = tips[Math.min(index, tips.length - 1)];

  return (
    <div
      className="mx-auto w-full max-w-[560px] max-md:max-w-none"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <button
        type="button"
        onClick={() => onFill(tip.fill)}
        className="group flex h-[224px] w-full flex-col items-center justify-center gap-3 rounded-sheet border border-divider-strong bg-surface px-6 py-7 text-center transition-[transform,border-color,box-shadow] hover:-translate-y-px hover:border-accent hover:shadow-e2 max-md:h-[232px] max-md:px-5 max-md:py-6"
      >
        <span className="grid h-11 w-11 place-items-center rounded-sheet bg-accent/10 text-accent">
          <Icon name={tip.icon} size={20} />
        </span>
        <span className="flex h-[22px] items-center whitespace-nowrap text-headline font-bold text-fg">{tip.title}</span>
        <span className="flex h-[42px] max-w-[420px] items-center justify-center overflow-hidden text-body leading-[1.55] text-muted max-md:h-[62px]">
          <span className="overflow-hidden [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:2] max-md:[-webkit-line-clamp:3]">
            {tip.body}
          </span>
        </span>
        <span className="mt-1 inline-flex h-[18px] max-w-full items-center gap-1 truncate text-footnote font-medium text-accent opacity-0 transition-opacity group-hover:opacity-100">
          {tip.fill}
        </span>
      </button>

      {tips.length > 1 && (
        <div className="mt-4 flex justify-center gap-2">
          {tips.map((t, i) => (
            <button
              key={t.title}
              type="button"
              aria-label={t.title}
              aria-current={i === index ? "true" : undefined}
              onClick={() => setIndex(i)}
              className={
                i === index
                  ? "h-1.5 w-5 rounded-full bg-accent transition-all"
                  : "h-1.5 w-1.5 rounded-full bg-divider-strong transition-all hover:bg-muted"
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}
