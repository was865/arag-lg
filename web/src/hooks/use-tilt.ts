"use client";

import { useMemo } from "react";
import { tiltFor } from "@/lib/ambient";

/**
 * カードをポインタに合わせてわずかに傾ける（globals.css の .tilt と組で使う）。
 * 返り値をそのまま要素に広げる: `<button className="tilt relative ..." {...tilt}>`。
 * マウスのときだけ動かす（タッチでは指の下で傾くと押しにくい）。React の状態は使わず、CSS 変数だけを書き換える。
 */
export function useTilt(maxDeg = 4) {
  return useMemo(
    () => ({
      onPointerMove: (e: React.PointerEvent<HTMLElement>) => {
        if (e.pointerType !== "mouse") return;
        const el = e.currentTarget;
        const r = el.getBoundingClientRect();
        const px = (e.clientX - r.left) / r.width;
        const py = (e.clientY - r.top) / r.height;
        const { rx, ry } = tiltFor(px, py, maxDeg);
        el.style.setProperty("--rx", `${rx.toFixed(2)}deg`);
        el.style.setProperty("--ry", `${ry.toFixed(2)}deg`);
        el.style.setProperty("--mx", `${(px * 100).toFixed(1)}%`);
        el.style.setProperty("--my", `${(py * 100).toFixed(1)}%`);
        el.setAttribute("data-tilting", "");
      },
      onPointerLeave: (e: React.PointerEvent<HTMLElement>) => {
        const el = e.currentTarget;
        el.style.setProperty("--rx", "0deg");
        el.style.setProperty("--ry", "0deg");
        el.removeAttribute("data-tilting");
      },
    }),
    [maxDeg],
  );
}
