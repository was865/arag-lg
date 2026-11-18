"use client";

/**
 * スクロールする要素の「続き」がどの向きにあるか（表の右端の影・根拠の列の端を薄くする合図に使う）。
 * 合図の見た目は globals.css の @utility scroll-fade-x / scroll-fade-y（data-more-* を見る）か、使う側で描く。
 */
import { useCallback, useEffect, useRef, useState } from "react";

export interface OverflowState {
  top: boolean;
  bottom: boolean;
  left: boolean;
  right: boolean;
}

const NONE: OverflowState = { top: false, bottom: false, left: false, right: false };

/** スクロール量から上下左右に「続き」があるかを判定する。端数は 1px まで許容。 */
export function computeOverflow(m: {
  scrollLeft: number;
  scrollWidth: number;
  clientWidth: number;
  scrollTop?: number;
  scrollHeight?: number;
  clientHeight?: number;
}): OverflowState {
  const EPS = 1;
  const maxX = m.scrollWidth - m.clientWidth;
  const maxY = (m.scrollHeight ?? 0) - (m.clientHeight ?? 0);
  const y = m.scrollTop ?? 0;
  return {
    top: y > EPS,
    bottom: y < maxY - EPS,
    left: m.scrollLeft > EPS,
    right: m.scrollLeft < maxX - EPS,
  };
}

/** 要素に付ける data-more-*（続きのある向きだけ）。scroll-fade-* がこれを見る。 */
export function overflowData(o: OverflowState) {
  return {
    "data-more-top": o.top || undefined,
    "data-more-bottom": o.bottom || undefined,
    "data-more-left": o.left || undefined,
    "data-more-right": o.right || undefined,
  };
}

/**
 * スクロールする要素の上下左右の続きを返すフック。
 * scroll とサイズ変化（ResizeObserver。中身の増減も見る）の両方で測り直す。
 */
export function useOverflow<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [overflow, setOverflow] = useState<OverflowState>(NONE);

  const measure = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const next = computeOverflow(el);
    setOverflow((prev) =>
      prev.top === next.top && prev.bottom === next.bottom && prev.left === next.left && prev.right === next.right
        ? prev
        : next,
    );
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    measure();
    el.addEventListener("scroll", measure, { passive: true });
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    for (const child of el.children) ro.observe(child);
    return () => {
      el.removeEventListener("scroll", measure);
      ro.disconnect();
    };
  }, [measure]);

  return { ref, overflow, measure };
}
