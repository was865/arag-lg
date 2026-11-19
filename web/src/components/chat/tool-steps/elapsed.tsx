"use client";
/** 問い合わせ中の経過の秒（specs/033 R18）。この画面が見始めてからの秒を 1 秒ごとに数える（作った動きではない）。 */
import { useEffect, useState } from "react";
import { useT } from "@/i18n/context";
import { interpolate } from "@/i18n/interpolate";

export function Elapsed({ className }: { className?: string }) {
  const { t } = useT();
  const [s, setS] = useState(0);
  useEffect(() => {
    const t0 = Date.now();
    const id = setInterval(() => setS(Math.floor((Date.now() - t0) / 1000)), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <span className={className} aria-live="off">
      {interpolate(t.chat.systemQuerying, { s: String(s) })}
    </span>
  );
}
