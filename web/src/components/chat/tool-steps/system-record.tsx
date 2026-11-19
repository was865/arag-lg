/** 社内システム（MCP）の結果の表示（specs/032 R20・R23）。「詳細」のステップと出典パネルで使う。 */
import type { Dictionary } from "@/i18n/dictionary";
import { interpolate } from "@/i18n/interpolate";
import { formatFetchedAt } from "@/lib/datetime";
import type { SystemRecord } from "@/lib/types";
import { Ago } from "./ago";
import { KeyValueGrid } from "./shared";
import { DataTable } from "./table-result";

/** ステップの出力（middleware が足す system・columns・rows…）から表示用の形にする。表でなければ null。 */
export function recordFromOutput(o: Record<string, unknown>): SystemRecord | null {
  if (!Array.isArray(o.columns) || !Array.isArray(o.rows)) return null;
  return {
    system: String(o.system ?? ""),
    fetchedAt: String(o.fetched_at ?? ""),
    basis: typeof o.basis === "string" ? o.basis : undefined,
    columns: o.columns.map(String),
    rows: o.rows as unknown[][],
    total: typeof o.total === "number" ? o.total : o.rows.length,
    tool: typeof o.tool === "string" ? o.tool : undefined,
    args: o.args && typeof o.args === "object" ? (o.args as Record<string, unknown>) : undefined,
    restricted: Array.isArray(o.restricted) ? o.restricted.map(String) : undefined,
    note: typeof o.note === "string" ? o.note : undefined,
  };
}

export function SystemRecordView({ record, t, meta = true }: { record: SystemRecord; t: Dictionary; meta?: boolean }) {
  const rows: { k: string; v: React.ReactNode }[] = [];
  if (meta) {
    const fetched = formatFetchedAt(record.fetchedAt);
    rows.push({
      k: t.chat.systemFetchedAt,
      v: (
        <span>
          {fetched}
          <Ago iso={record.fetchedAt} className="ml-1.5 text-muted" />
        </span>
      ),
    });
    // 「ERP の現在の値（… 取得）」のように取得の時刻を言い直すだけの時点は重ねて出さない
    if (record.basis && !(fetched && record.basis.includes(fetched))) rows.push({ k: t.chat.systemBasis, v: record.basis });
    if (record.tool) rows.push({ k: t.chat.systemTool, v: record.tool });
    const args = Object.entries(record.args ?? {}).filter(([, v]) => v !== "" && v != null);
    if (args.length) rows.push({ k: t.chat.systemArgs, v: args.map(([k, v]) => `${k}=${String(v)}`).join("・") });
  }
  const shown = record.rows.length;
  return (
    <div className="space-y-2">
      {rows.length > 0 && <KeyValueGrid rows={rows} />}
      {record.columns.length > 0 && shown > 0 ? (
        <DataTable nowrap rows={[record.columns, ...record.rows.map((r) => r.map((c) => (c == null ? "" : String(c))))]} />
      ) : (
        <div className="text-footnote text-muted">{t.chat.systemNoRows}</div>
      )}
      <div className="text-caption text-muted">
        {shown < record.total
          ? interpolate(t.chat.systemRowsShown, { n: String(shown), m: String(record.total) })
          : interpolate(t.chat.systemRowsAll, { n: String(record.total) })}
      </div>
      {(record.restricted?.length ?? 0) > 0 && (
        <div className="text-caption text-muted">
          {interpolate(t.chat.systemRestricted, { cols: (record.restricted ?? []).join("・") })}
        </div>
      )}
      {record.note && <div className="text-caption text-muted">{record.note}</div>}
    </div>
  );
}
