"use client";

import { useState } from "react";
import { parseTableHtml, type InlineSegment } from "@/components/sources/parse-table-html";
import { TeXText } from "@/components/sources/tex-text";
import { useOverflow } from "@/components/sources/use-overflow";
import { TableSheet } from "@/components/sources/table-sheet";
import { cn } from "@/lib/utils";
import { useT } from "@/i18n/context";
import { cellFit, numericColumns } from "@/components/sources/table-layout";

function Seg({ s, renderMath }: { s: InlineSegment; renderMath?: boolean }) {
  const cls = cn(s.bold && "font-semibold", s.italic && "italic", s.underline && "underline");
  if (s.href) {
    return (
      <a href={s.href} target="_blank" rel="noopener noreferrer" className={cn(cls, "text-accent underline")}>
        {s.text}
      </a>
    );
  }
  const content = renderMath ? <TeXText text={s.text} /> : s.text;
  return cls ? <span className={cls}>{content}</span> : <>{content}</>;
}

function Lines({ lines, renderMath }: { lines: InlineSegment[][]; renderMath?: boolean }) {
  return (
    <>
      {lines.map((line, i) => (
        <span key={i} className="block">
          {line.map((s, j) => <Seg key={j} s={s} renderMath={renderMath} />)}
        </span>
      ))}
    </>
  );
}

/** テーブルHTML文字列を整形描画する。解析できない場合は素のテキストにフォールバック。
 *  renderMath=true でセル内の TeX 数式を KaTeX 描画する（既定は無効＝引用パネルの通貨 $ 誤爆を避ける）。 */
export function HtmlTable({ html, className, renderMath }: { html: string; className?: string; renderMath?: boolean }) {
  const { t } = useT();
  const model = parseTableHtml(html);
  const { ref, overflow } = useOverflow<HTMLDivElement>();
  const [sheetOpen, setSheetOpen] = useState(false);

  if (!model) {
    return <div className={cn("whitespace-pre-wrap text-[12.5px] leading-[1.65] text-fg-2 [overflow-wrap:anywhere]", className)}>{html}</div>;
  }

  const wide = overflow.left || overflow.right;
  const numeric = numericColumns(model);
  // 先頭列が見出し（設備ID など）のときは横スクロールしても残す
  const stickFirst = wide && model.rows.length > 1 && model.rows.every((r) => r.cells[0]?.colspan === 1);

  const table = (sheet: boolean) => (
    <table className="w-full border-separate border-spacing-0 text-[11.5px] leading-[1.55]">
      <tbody>
        {model.rows.map((row, ri) => {
          const last = ri === model.rows.length - 1;
          return (
            <tr key={ri}>
              {row.cells.map((c, ci) => {
                const Tag = c.header ? "th" : "td";
                const fit = cellFit(c);
                const right = numeric.has(ci) && (fit === "numeric" || c.header);
                const sticky = !sheet && stickFirst && ci === 0;
                return (
                  <Tag
                    key={ci}
                    colSpan={c.colspan}
                    rowSpan={c.rowspan}
                    className={cn(
                      "px-3 py-[7px] align-top",
                      // 区切りは細い横線と縦線だけ（外枠はラッパが持つ）
                      !last && "border-b-[0.5px] border-divider",
                      ci < row.cells.length - 1 && "border-r-[0.5px] border-divider",
                      c.header ? "bg-surface-2 text-left text-[11px] font-semibold text-fg" : "bg-surface text-fg-2",
                      // 数値・短い語は 1 行に収め、長い文だけ読みやすい幅で折り返す
                      fit === "long" ? "min-w-[9em] max-w-[24em] [overflow-wrap:anywhere]" : "whitespace-nowrap",
                      right && "text-right tabular-nums",
                      sticky && "sticky left-0 z-[1]",
                      sticky && overflow.left && "shadow-[6px_0_8px_-6px_var(--edge-shadow)]",
                    )}
                  >
                    <Lines lines={c.lines} renderMath={renderMath} />
                  </Tag>
                );
              })}
            </tr>
          );
        })}
      </tbody>
    </table>
  );

  return (
    <div
      className={cn(
        "group/tbl relative min-w-0 overflow-hidden rounded-[10px] border-[0.5px] border-divider-strong bg-surface",
        className,
      )}
    >
      <div
        ref={ref}
        data-overflow-left={overflow.left}
        data-overflow-right={overflow.right}
        className="overflow-x-auto [scrollbar-width:thin]"
      >
        {table(false)}
      </div>

      {/* 右に続きがある合図: 地の色に依存しない細い影だけ（強調表示の上でも濁らない） */}
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute inset-y-0 right-0 w-4 bg-gradient-to-l from-[var(--edge-shadow)] to-transparent transition-opacity duration-200",
          overflow.right ? "opacity-100" : "opacity-0",
        )}
      />

      {/* 拡大は横に広い表だけ。ふだんは隠し、表に触れたときだけ角に出す（モバイルはホバーが無いので常時） */}
      {wide && (
        <button
          type="button"
          onClick={() => setSheetOpen(true)}
          title={t.sources.expandTable}
          aria-label={t.sources.expandTable}
          className="absolute right-1.5 top-1.5 z-[2] grid h-6 w-6 place-items-center rounded-[6px] bg-surface-elev text-muted opacity-0 shadow-e1 ring-[0.5px] ring-divider-strong transition-opacity duration-150 hover:text-fg focus-visible:opacity-100 group-hover/tbl:opacity-100 max-md:opacity-100"
        >
          <svg viewBox="0 0 16 16" width="11" height="11" aria-hidden>
            <path d="M9.5 2.5h4v4M6.5 13.5h-4v-4M13.5 2.5 9 7M2.5 13.5 7 9" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      )}

      {sheetOpen && <TableSheet onClose={() => setSheetOpen(false)}>{table(true)}</TableSheet>}
    </div>
  );
}
