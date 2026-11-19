"use client";

/**
 * いま何をしているかを示す小さな絵（回るだけの輪の代わり）。
 * - 検索は虫眼鏡が探るように動き、読むときは文書の上を線が走り、考えるときは点が波打つ、など。
 * - 種類が変わるときは、前の絵が縮んでぼけながら消え、次の絵がばねで入る（つながって見える）。
 * - 動きは CSS（globals.css の ar-g-*）。「視差効果を減らす」では止まり、絵だけが切り替わる。
 */
import { AnimatePresence, m } from "motion/react";
import type { ToolName } from "@/lib/types";
import { cn } from "@/lib/utils";

export type Activity =
  | "understand"
  | "search"
  | "read"
  | "table"
  | "calc"
  | "think"
  | "write"
  | "check"
  | "image"
  | "switch"
  | "tool";

/** ステップの種類から、絵の種類へ。 */
export function activityOf(name: ToolName | undefined): Activity {
  switch (name) {
    case "understand":
    case "rewrite_query":
      return "understand";
    case "retrieve":
    case "vector_search":
    case "bm25_search":
    case "rerank":
    case "embed":
    case "expand":
    case "grade":
    case "web_search":
      return "search";
    case "fetch_document":
    case "summarize":
      return "read";
    case "table_query":
    case "system_query":
    case "sql_query":
      return "table";
    case "calculate":
      return "calc";
    case "reasoning":
      return "think";
    case "answer":
    case "revise":
      return "write";
    case "review":
    case "verify":
      return "check";
    case "read_image":
      return "image";
    case "switch_model":
      return "switch";
    default:
      return "tool";
  }
}

const stroke = { stroke: "currentColor", strokeWidth: 1.5, fill: "none", strokeLinecap: "round", strokeLinejoin: "round" } as const;

const GLYPHS: Record<Activity, React.ReactNode> = {
  // 虫眼鏡が小さく円を描いて探る
  search: (
    <g className="ar-g-orbit">
      <circle cx="7" cy="7" r="3.6" {...stroke} />
      <path d="M9.8 9.8l3 3" {...stroke} />
    </g>
  ),
  // 文書の上を、読む線が上から下へ走る
  read: (
    <>
      <path d="M4 2h5.5L12 4.5V14H4V2z" {...stroke} strokeWidth={1.3} />
      <path d="M6 6h4" {...stroke} strokeWidth={1.3} className="ar-g-scan" />
    </>
  ),
  // 表のマスが順に灯る
  table: (
    <>
      <rect x="2" y="3" width="12" height="10" rx="1.5" {...stroke} strokeWidth={1.3} />
      <path d="M2 8h12M8 3v10" {...stroke} strokeWidth={1.1} />
      {[
        [3, 4],
        [9, 4],
        [9, 9],
        [3, 9],
      ].map(([x, y], i) => (
        <rect key={i} x={x} y={y} width="4" height="3" rx="0.5" fill="currentColor" className="ar-g-cell" style={{ animationDelay: `${i * 0.22}s` }} />
      ))}
    </>
  ),
  // 計算機の表示が明滅し、キーが順に押される
  calc: (
    <>
      <rect x="3.5" y="1.8" width="9" height="12.4" rx="1.5" {...stroke} strokeWidth={1.3} />
      <path d="M5.8 4.8h4.4" {...stroke} className="ar-g-cell" />
      {[5.8, 8, 10.2].map((x, i) => (
        <circle key={x} cx={x} cy="9.6" r="0.9" fill="currentColor" className="ar-g-dot" style={{ animationDelay: `${i * 0.15}s` }} />
      ))}
    </>
  ),
  // 3 つの点が波のように上下する
  think: (
    <>
      {[3.6, 8, 12.4].map((x, i) => (
        <circle key={x} cx={x} cy="8.5" r="1.45" fill="currentColor" className="ar-g-dot" style={{ animationDelay: `${i * 0.16}s` }} />
      ))}
    </>
  ),
  // ペンが揺れ、下に線が引かれていく
  write: (
    <>
      <g className="ar-g-rock" style={{ transformOrigin: "5px 11px" }}>
        <path d="M10.6 2.8l2.4 2.4-6.2 6.2-2.9.6.6-2.9 6.1-6.3z" {...stroke} strokeWidth={1.3} />
      </g>
      <path d="M8 14h5.5" {...stroke} strokeWidth={1.3} pathLength={1} className="ar-g-draw" />
    </>
  ),
  // 盾の中で、確認の印が描かれる
  check: (
    <>
      <path d="M8 1.8l4.6 1.8v3.7c0 2.8-1.9 4.8-4.6 5.7-2.7-.9-4.6-2.9-4.6-5.7V3.6L8 1.8z" {...stroke} strokeWidth={1.3} />
      <path d="M5.9 7.6l1.6 1.6 2.7-3" {...stroke} pathLength={1} className="ar-g-draw" />
    </>
  ),
  // 吹き出しの上で、光がまたたく
  understand: (
    <>
      <path d="M2.3 4h7.4a1.5 1.5 0 0 1 1.5 1.5v3.7a1.5 1.5 0 0 1-1.5 1.5H6.6l-2.6 2v-2h-.2a1.5 1.5 0 0 1-1.5-1.5V4z" {...stroke} strokeWidth={1.3} />
      <path d="M12.6 1.2l.6 1.5 1.5.6-1.5.6-.6 1.5-.6-1.5-1.5-.6 1.5-.6.6-1.5z" fill="currentColor" className="ar-g-twinkle" style={{ transformOrigin: "12.6px 3.3px" }} />
    </>
  ),
  // 画像の上を、読み取りの線が走る
  image: (
    <>
      <rect x="2" y="3" width="12" height="10" rx="1.5" {...stroke} strokeWidth={1.3} />
      <path d="M2.6 11l3.2-2.8 2.4 1.9 2-1.5 3.2 2.6" {...stroke} strokeWidth={1.2} />
      <path d="M3.5 5h9" {...stroke} strokeWidth={1.2} className="ar-g-scan" />
    </>
  ),
  // 2 本の矢印が行き交う
  switch: (
    <>
      <path d="M3 5.4h9l-2.3-2.3" {...stroke} className="ar-g-slide" />
      <path d="M13 10.6H4l2.3 2.3" {...stroke} className="ar-g-slide-back" />
    </>
  ),
  // 歯車がゆっくり回る
  tool: (
    <g className="ar-g-turn" style={{ transformOrigin: "8px 8px" }}>
      <circle cx="8" cy="8" r="2.3" {...stroke} strokeWidth={1.3} />
      <path d="M8 1.9v1.7M8 12.4v1.7M1.9 8h1.7M12.4 8h1.7M3.7 3.7l1.2 1.2M11.1 11.1l1.2 1.2M3.7 12.3l1.2-1.2M11.1 4.9l1.2-1.2" {...stroke} strokeWidth={1.3} />
    </g>
  ),
};

export function ActivityGlyph({ activity, size = 14, className }: { activity: Activity; size?: number; className?: string }) {
  return (
    <span className={cn("relative inline-grid shrink-0 place-items-center text-accent", className)} style={{ width: size + 2, height: size + 2 }} aria-hidden>
      <AnimatePresence initial={false} mode="popLayout">
        <m.span
          key={activity}
          className="col-start-1 row-start-1 grid place-items-center"
          initial={{ opacity: 0, scale: 0.5, rotate: -30, filter: "blur(3px)" }}
          animate={{ opacity: 1, scale: 1, rotate: 0, filter: "blur(0px)" }}
          exit={{ opacity: 0, scale: 0.5, rotate: 30, filter: "blur(3px)" }}
          transition={{ type: "spring", stiffness: 420, damping: 26, mass: 0.6 }}
        >
          <svg viewBox="0 0 16 16" width={size} height={size} className="overflow-visible">
            {GLYPHS[activity]}
          </svg>
        </m.span>
      </AnimatePresence>
    </span>
  );
}
