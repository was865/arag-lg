"use client";

/**
 * 首ページの後ろでゆっくり漂う光（Canvas）。アクセント色と、その色相を少しずらした 2 色の光が上のほうを漂う。
 * - 低い解像度で描いて CSS でぼかす（軽く、縞が出ない）。毎秒 30 コマまで。
 * - 画面が隠れている間は止める。OS の「視差効果を減らす」が有効なら 1 コマだけ描いて動かさない。
 * - 飾りなので読み上げからは隠す。画面の中で動く飾りはこれ 1 つだけ（specs/025 R4）。
 */
import { useEffect, useRef } from "react";
import { blobsAt, hexToRgb, rotateHue } from "@/lib/ambient";
import { cn } from "@/lib/utils";

/** 描く解像度（CSS ピクセルに対する割合）。ぼかすので粗くてよい */
const SCALE = 0.12;
const FRAME_MS = 1000 / 30;

export function AmbientGlow({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    let last = 0;
    // 開くたびに違う形から始める
    const offset = Math.random() * 600;

    const resize = () => {
      canvas.width = Math.max(1, Math.round(canvas.clientWidth * SCALE));
      canvas.height = Math.max(1, Math.round(canvas.clientHeight * SCALE));
    };

    const draw = (seconds: number) => {
      // 利用者が選んだアクセント色を毎コマ読む（設定で変えたらすぐ追従する）
      const accent = hexToRgb(getComputedStyle(document.documentElement).getPropertyValue("--accent"));
      const { width: w, height: h } = canvas;
      ctx.clearRect(0, 0, w, h);
      if (!accent) return;
      for (const b of blobsAt(seconds + offset)) {
        const [r, g, bl] = rotateHue(accent, b.hue);
        const radius = b.r * w;
        const grad = ctx.createRadialGradient(b.x * w, b.y * h, 0, b.x * w, b.y * h, radius);
        grad.addColorStop(0, `rgba(${r},${g},${bl},${b.alpha})`);
        grad.addColorStop(1, `rgba(${r},${g},${bl},0)`);
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, w, h);
      }
    };

    const tick = (now: number) => {
      raf = requestAnimationFrame(tick);
      if (now - last < FRAME_MS) return;
      last = now;
      draw(now / 1000);
    };

    const start = () => {
      cancelAnimationFrame(raf);
      if (reduce || document.hidden) draw(0);
      else raf = requestAnimationFrame(tick);
    };

    resize();
    start();
    const ro = new ResizeObserver(() => {
      resize();
      draw(performance.now() / 1000);
    });
    ro.observe(canvas);
    document.addEventListener("visibilitychange", start);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      document.removeEventListener("visibilitychange", start);
    };
  }, []);

  return (
    <canvas
      ref={ref}
      aria-hidden
      className={cn("pointer-events-none h-full w-full animate-fade-in opacity-40 blur-[48px] dark:opacity-35 motion-reduce:animate-none", className)}
    />
  );
}
