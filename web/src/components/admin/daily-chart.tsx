"use client";

/** 日ごとの質問数（回答あり・回答なしの積み上げ縦棒）。specs/012-analytics R3。 */
import { useEffect, useRef, useState } from "react";
import { niceMax, tickDates } from "@/lib/admin/analytics";

export interface DailyPoint {
  date: string;
  questions: number;
  no_answer: number;
}

const H = 200;
const PAD = { top: 8, right: 4, bottom: 22, left: 34 };
const GAP = 2; // 積み上げの区切り（面の色の隙間）

const dayFmt = new Intl.DateTimeFormat("ja-JP", { month: "numeric", day: "numeric", timeZone: "UTC" });
const fullFmt = new Intl.DateTimeFormat("ja-JP", {
  year: "numeric",
  month: "numeric",
  day: "numeric",
  weekday: "short",
  timeZone: "UTC",
});
const d = (s: string) => new Date(`${s}T00:00:00Z`);

/** 上の角だけ丸めた棒（基線側は四角）。 */
function bar(x: number, y: number, w: number, h: number, r: number) {
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`;
}

export function DailyChart({ data }: { data: DailyPoint[] }) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.floor(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const max = niceMax(Math.max(0, ...data.map((p) => p.questions)));
  const plotW = Math.max(0, width - PAD.left - PAD.right);
  const plotH = H - PAD.top - PAD.bottom;
  const band = data.length ? plotW / data.length : 0;
  const bw = Math.max(2, Math.min(24, band - GAP));
  const y = (v: number) => PAD.top + plotH - (v / max) * plotH;
  const ticks = [0, max / 4, max / 2, (max * 3) / 4, max];
  const xTicks = new Set(tickDates(data.map((p) => p.date), width < 520 ? 4 : 7));
  const hp = hover === null ? null : data[hover];

  return (
    <div ref={box} className="relative" onMouseLeave={() => setHover(null)}>
      {width > 0 && (
        <svg width={width} height={H} role="img" aria-label="日ごとの質問数の棒グラフ" className="block">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--divider)" strokeWidth={1} />
              <text x={PAD.left - 6} y={y(t)} dy="0.32em" textAnchor="end" fontSize={10.5} fill="var(--muted)">
                {t.toLocaleString("en-US")}
              </text>
            </g>
          ))}
          {data.map((p, i) => {
            const cx = PAD.left + band * i + band / 2;
            const x = cx - bw / 2;
            const answered = p.questions - p.no_answer;
            const hA = (answered / max) * plotH;
            const hN = (p.no_answer / max) * plotH;
            const base = PAD.top + plotH;
            const dim = hover !== null && hover !== i;
            return (
              <g key={p.date} opacity={dim ? 0.45 : 1}>
                {answered > 0 && (
                  <path
                    d={p.no_answer > 0 ? `M${x},${base}h${bw}v${-hA}h${-bw}Z` : bar(x, base - hA, bw, hA, 4)}
                    fill="var(--chart-1)"
                  />
                )}
                {p.no_answer > 0 && (
                  <path
                    d={bar(x, base - hA - hN - (answered > 0 ? GAP : 0), bw, hN, 4)}
                    fill="var(--chart-2)"
                  />
                )}
                {xTicks.has(p.date) && (
                  <text x={cx} y={H - 6} textAnchor="middle" fontSize={10.5} fill="var(--muted)">
                    {dayFmt.format(d(p.date))}
                  </text>
                )}
                {/* 当たり判定は帯全体 */}
                <rect
                  x={PAD.left + band * i}
                  y={PAD.top}
                  width={band}
                  height={plotH}
                  fill="transparent"
                  onMouseEnter={() => setHover(i)}
                  onClick={() => setHover(i)}
                />
              </g>
            );
          })}
          <line
            x1={PAD.left}
            x2={width - PAD.right}
            y1={PAD.top + plotH}
            y2={PAD.top + plotH}
            stroke="var(--divider-strong)"
            strokeWidth={1}
          />
        </svg>
      )}
      {hp && hover !== null && (
        <div
          role="tooltip"
          className="pointer-events-none absolute top-0 z-10 min-w-[150px] rounded-control border-[0.5px] border-divider-strong bg-surface-elev px-3 py-2 text-footnote shadow-e2"
          style={{
            left: Math.min(Math.max(0, PAD.left + band * hover + band / 2 - 75), Math.max(0, width - 160)),
          }}
        >
          <div className="mb-1 font-semibold text-fg">{fullFmt.format(d(hp.date))}</div>
          <Row color="var(--chart-1)" label="回答あり" value={hp.questions - hp.no_answer} />
          <Row color="var(--chart-2)" label="回答なし" value={hp.no_answer} />
          <div className="mt-1 flex justify-between border-t-[0.5px] border-divider pt-1 text-muted">
            <span>合計</span>
            <span className="font-mono text-fg">{hp.questions.toLocaleString("en-US")}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ color, label, value }: { color: string; label: string; value: number }) {
  return (
    <div className="flex items-center gap-2 text-fg-2">
      <span className="h-2 w-2 rounded-[2px]" style={{ background: color }} />
      <span className="flex-1">{label}</span>
      <span className="font-mono text-fg">{value.toLocaleString("en-US")}</span>
    </div>
  );
}

export function ChartLegend() {
  return (
    <div className="flex items-center gap-3 text-caption text-muted">
      {(
        [
          ["var(--chart-1)", "回答あり"],
          ["var(--chart-2)", "回答なし"],
        ] as const
      ).map(([c, l]) => (
        <span key={l} className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: c }} />
          {l}
        </span>
      ))}
    </div>
  );
}
