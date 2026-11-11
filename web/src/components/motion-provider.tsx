"use client";

/**
 * Motion の土台（specs/025 R5）。
 * - OS の「視差効果を減らす」が有効なら、Motion の動きはすべて即時になる（reducedMotion="user"）。
 * - LazyMotion で機能を必要な分だけ読み込む。strict なので部品では `motion.div` でなく `m.div` を使う。
 *   layout / layoutId を使うため domMax を読み込む。
 */
import { LazyMotion, MotionConfig, domMax } from "motion/react";
import { SPRING } from "@/lib/motion";

export function MotionProvider({ children }: { children: React.ReactNode }) {
  return (
    <LazyMotion features={domMax} strict>
      <MotionConfig reducedMotion="user" transition={SPRING}>
        {children}
      </MotionConfig>
    </LazyMotion>
  );
}
