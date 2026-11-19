/** 表の結果（table_query）の表示。Markdown の表を表として出す。 */
import { cn } from "@/lib/utils";
import type { Dictionary } from "@/i18n/dictionary";
import { KeyValueGrid, sectionLabelCls } from "./shared";

/** Markdown の表を含む文章（table_query の結果）。表は表として、ほかの行は文章として出す。 */
export function TableText({ text }: { text: string }) {
  const body = text.replace(/^<資料[^>]*>\n?/, "").replace(/\n?<\/資料>\s*$/, "");
  const blocks: ({ kind: "text"; lines: string[] } | { kind: "table"; rows: string[][] })[] = [];
  for (const line of body.split("\n")) {
    const isRow = line.trimStart().startsWith("|");
    const last = blocks[blocks.length - 1];
    if (isRow) {
      if (/^\s*\|[\s:|-]+\|\s*$/.test(line)) continue; // 区切り行
      const cells = line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      if (last?.kind === "table") last.rows.push(cells);
      else blocks.push({ kind: "table", rows: [cells] });
    } else if (line.trim()) {
      if (last?.kind === "text") last.lines.push(line);
      else blocks.push({ kind: "text", lines: [line] });
    }
  }
  return (
    <div className="space-y-2">
      {blocks.map((b, i) =>
        b.kind === "text" ? (
          <div key={i} className="whitespace-pre-wrap break-words text-footnote leading-[1.55] text-fg-2">
            {b.lines.join("\n")}
          </div>
        ) : (
          <DataTable key={i} rows={b.rows} />
        ),
      )}
    </div>
  );
}

/** 表（1 行目が見出し）。数の列は右寄せ。nowrap はセルを折り返さず横に滑らせる（社内システムの短い値の表）。 */
export function DataTable({ rows, nowrap = false }: { rows: string[][]; nowrap?: boolean }) {
  return (
    <div className="overflow-x-auto rounded-control border-[0.5px] border-divider bg-code-bg">
      <table className="w-full border-collapse text-caption">
        <thead>
          <tr>
            {rows[0].map((c, j) => (
              <th key={j} className="whitespace-nowrap border-b-[0.5px] border-divider-strong px-2.5 py-1.5 text-left font-semibold text-fg">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(1).map((r, k) => (
            <tr key={k} className="border-t-[0.5px] border-divider first:border-t-0">
              {r.map((c, j) => (
                <td key={j} className={cn("px-2.5 py-1.5 text-fg-2", nowrap && "whitespace-nowrap", /^-?[\d,.]+$/.test(c) && "text-right font-mono tabular-nums")}>
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export type Stats = { sum: string; avg: string; max: string; min: string };

/**
 * 表の集計の結果（specs/028 R10）。該当行の表 → 該当 n 行 / 全 m 行 → compute の列の集計、
 * ほかの列の集計は「すべての集計」（既定は閉）。構造の無い古い記録は、モデルに渡した文のまま出す。
 */
export function TableResult({ output, t }: { output: Record<string, unknown>; t: Dictionary }) {
  const { rows, columns, rows_matched: matched, rows_total: total } = output;
  if (!Array.isArray(rows) || !Array.isArray(columns) || typeof matched !== "number" || typeof total !== "number") {
    return typeof output.result === "string" ? <TableText text={output.result} /> : null;
  }
  const label = typeof output.compute_label === "string" ? output.compute_label : null;
  const aggs = (output.aggregates ?? {}) as Record<string, Stats>;
  const main = label ? aggs[label] : undefined;
  const others = Object.entries(aggs).filter(([k]) => k !== label);
  const statRows = (a: Stats) => [
    { k: t.chat.aggSum, v: a.sum },
    { k: t.chat.aggAvg, v: a.avg },
    { k: t.chat.aggMax, v: a.max },
    { k: t.chat.aggMin, v: a.min },
  ];
  return (
    <div className="space-y-2">
      {rows.length > 0 && <DataTable rows={[columns.map(String), ...(rows as unknown[][]).map((r) => r.map(String))]} />}
      <div className="text-caption text-muted">
        {t.chat.tableMatched.replace("{n}", String(matched)).replace("{m}", String(total))}
      </div>
      {Array.isArray(output.notes) && output.notes.length > 0 && (
        <div className="text-caption text-muted">
          <span className={sectionLabelCls}>{t.chat.tableNotes}</span>
          {(output.notes as unknown[]).map((n, i) => (
            <p key={i}>{String(n)}</p>
          ))}
        </div>
      )}
      {label && output.compute_value !== undefined && (
        <KeyValueGrid rows={[{ k: label, v: output.compute_value === null ? "—" : String(output.compute_value) }]} />
      )}
      {label && main && (
        <div>
          <div className={sectionLabelCls}>{label}</div>
          <KeyValueGrid rows={statRows(main)} />
        </div>
      )}
      {others.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-caption text-muted outline-none hover:text-fg-2 focus-visible:ring-2 focus-visible:ring-accent/50">
            {t.chat.tableAllAggregates}
          </summary>
          <div className="mt-2">
            <DataTable
              rows={[
                [t.chat.tableColumn, t.chat.aggSum, t.chat.aggAvg, t.chat.aggMax, t.chat.aggMin],
                ...others.map(([k, a]) => [k, a.sum, a.avg, a.max, a.min]),
              ]}
            />
          </div>
        </details>
      )}
    </div>
  );
}
