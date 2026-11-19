"use client";
/** 取得の時点の経過「12 秒前」を出し続ける（specs/033 R16）。秒の間は 1 秒ごと、その後は 1 分ごとに描き直す。 */
import { useEffect, useState } from "react";
import { ago, agoTick } from "@/lib/datetime";

export function Ago({ iso, className }: { iso: string; className?: string }) {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const tick = () => {
      const d = new Date();
      setNow(d);
      timer = setTimeout(tick, agoTick(iso, d));
    };
    tick();
    return () => clearTimeout(timer);
  }, [iso]);
  // サーバーの描画と最初の描画では出さない（時刻の差で hydration が食い違うため）
  const text = now ? ago(iso, now) : "";
  if (!text) return null;
  return (
    <time dateTime={iso} className={className} suppressHydrationWarning>
      {text}
    </time>
  );
}
