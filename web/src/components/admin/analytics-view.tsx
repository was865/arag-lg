"use client";

/** 利用状況の分析（specs/012-analytics R5）。 */
import createClient from "openapi-fetch";
import { useEffect, useState } from "react";
import { AdminHeader } from "@/components/admin/admin-header";
import { ChartLegend, DailyChart } from "@/components/admin/daily-chart";
import type { components, paths } from "@/lib/api/schema";
import {
  compact,
  formatDuration,
  formatRate,
  PERIODS,
  reasonLabel,
  tagLabel,
  type Period,
} from "@/lib/admin/analytics";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";

type Data = components["schemas"]["AnalyticsOut"];
const client = createClient<paths>({ baseUrl: "/api" });

const dateTimeFmt = new Intl.DateTimeFormat("ja-JP", {
  month: "numeric",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export function AnalyticsView() {
  const [days, setDays] = useState<Period>(30);
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [table, setTable] = useState(false);

  useEffect(() => {
    let alive = true;
    client.GET("/v1/admin/analytics", { params: { query: { days } } }).then(({ data: d, error: e }) => {
      if (!alive) return;
      if (d) {
        setData(d);
        setError(null);
      } else {
        const msg = (e as { error?: { message?: string } } | undefined)?.error?.message;
        setError(msg ?? "分析を取得できませんでした");
      }
    });
    return () => {
      alive = false;
    };
  }, [days]);

  const t = data?.totals;
  return (
    <div className="grid h-dvh grid-cols-[minmax(0,1fr)] grid-rows-[auto_1fr] bg-bg">
      <AdminHeader current="analytics">
        <div className="max-md:hidden">
          <PeriodPicker value={days} onChange={setDays} />
        </div>
      </AdminHeader>

      <div className="min-h-0 overflow-y-auto">
        <div className="mx-auto flex max-w-[1100px] flex-col gap-4 px-[18px] pb-12 pt-4 max-md:px-3">
          <div className="md:hidden">
            <PeriodPicker value={days} onChange={setDays} />
          </div>
          {error && <p className="m-0 text-footnote text-danger">{error}</p>}
          {!data && !error ? (
            <div className="grid h-60 place-items-center">
              <span className="h-6 w-6 animate-[ar-spin_0.8s_linear_infinite] rounded-full border-2 border-divider-strong border-t-accent" />
            </div>
          ) : data && t ? (
            <>
              <section aria-label="概要" className="grid grid-cols-5 gap-3 max-lg:grid-cols-3 max-md:grid-cols-2">
                <Tile label="質問" value={compact(t.questions)} />
                <Tile label="利用した人" value={compact(t.users)} />
                <Tile label="回答できた割合" value={formatRate(t.answered_rate)} />
                <Tile label="回答までの時間（中央値）" value={formatDuration(t.median_duration_ms)} />
                <Tile
                  label="トークン（入力 / 出力）"
                  value={`${compact(t.tokens_in)} / ${compact(t.tokens_out)}`}
                  small
                />
              </section>

              <Card
                title="日ごとの質問"
                action={
                  <div className="flex items-center gap-3">
                    <ChartLegend />
                    <Button variant="ghost" size="sm" className="h-6 text-caption text-muted hover:text-fg"
                      onClick={() => setTable((x) => !x)}
                      aria-pressed={table}
                    >
                      {table ? "グラフで見る" : "表で見る"}
                    </Button>
                  </div>
                }
              >
                {table ? (
                  <div className="max-h-[260px] overflow-y-auto">
                    <table className="w-full text-footnote">
                      <thead className="sticky top-0 bg-surface text-left text-muted">
                        <tr>
                          <th className="py-1 font-medium">日付</th>
                          <th className="py-1 text-right font-medium">質問</th>
                          <th className="py-1 text-right font-medium">回答なし</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[...data.daily].reverse().map((p) => (
                          <tr key={p.date} className="border-t-[0.5px] border-divider">
                            <td className="py-1 font-mono text-fg-2">{p.date}</td>
                            <td className="py-1 text-right font-mono text-fg">{p.questions}</td>
                            <td className="py-1 text-right font-mono text-fg">{p.no_answer}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <DailyChart data={data.daily} />
                )}
              </Card>

              <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
                <Card title="回答できなかった質問">
                  {data.no_answer_reasons.length === 0 ? (
                    <Empty>この期間に回答できなかった質問はありません</Empty>
                  ) : (
                    <>
                      <Bars
                        items={data.no_answer_reasons.map((r) => ({ label: reasonLabel(r.reason), value: r.count }))}
                      />
                      <h4 className="mb-1 mt-4 text-caption font-semibold text-muted">最近の質問</h4>
                      <ul className="m-0 max-h-[240px] list-none overflow-y-auto p-0">
                        {data.recent_gaps.map((g, i) => (
                          <li
                            key={`${g.created_at}-${i}`}
                            className="flex items-baseline gap-2 border-t-[0.5px] border-divider py-1.5 text-footnote max-md:flex-wrap"
                          >
                            <span className="min-w-0 flex-1 break-words text-fg max-md:basis-full">{g.query}</span>
                            <span className="shrink-0 text-caption text-muted">{reasonLabel(g.reason)}</span>
                            <span className="shrink-0 font-mono text-caption text-muted-2">
                              {dateTimeFmt.format(new Date(g.created_at))}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </Card>

                <Card title="回答への評価">
                  {data.feedback.up + data.feedback.down === 0 ? (
                    <Empty>この期間の評価はまだありません</Empty>
                  ) : (
                    <>
                      <div className="flex gap-6">
                        <Figure label="👍 良い" value={data.feedback.up} />
                        <Figure label="👎 良くない" value={data.feedback.down} />
                        <Figure
                          label="良い評価の割合"
                          text={formatRate(data.feedback.up / (data.feedback.up + data.feedback.down))}
                        />
                      </div>
                      {data.feedback.top_down_tags.length > 0 && (
                        <>
                          <h4 className="mb-1 mt-4 text-caption font-semibold text-muted">良くない理由</h4>
                          <Bars
                            items={data.feedback.top_down_tags.map((x) => ({ label: tagLabel(x.tag), value: x.count }))}
                          />
                        </>
                      )}
                    </>
                  )}
                </Card>
              </div>

              <Card title="よく引用された文書">
                {data.top_documents.length === 0 ? (
                  <Empty>この期間に引用された文書はありません</Empty>
                ) : (
                  <table className="w-full text-footnote">
                    <thead className="text-left text-caption text-muted">
                      <tr>
                        <th className="py-1 font-medium">文書</th>
                        <th className="w-[90px] py-1 text-right font-medium">引用</th>
                        <th className="w-[90px] py-1 text-right font-medium">回答</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.top_documents.map((doc) => (
                        <tr key={doc.title} className="border-t-[0.5px] border-divider">
                          <td className="max-w-0 truncate py-1.5 pr-2 text-fg" title={doc.title}>
                            {doc.title}
                          </td>
                          <td className="py-1.5 text-right font-mono text-fg">{doc.citations}</td>
                          <td className="py-1.5 text-right font-mono text-fg-2">{doc.answers}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Card>
              <p className="m-0 text-caption text-muted-2">
                日付は UTC で区切っています。数値は完了または中断された質問を数えています。
              </p>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function Tile({ label, value, small }: { label: string; value: string; small?: boolean }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-[12px] border-[0.5px] border-divider bg-surface px-4 py-3">
      <span className="truncate text-caption text-muted">{label}</span>
      <span className={cn("truncate font-display font-bold text-fg", small ? "text-title leading-[28px]" : "text-display")}>
        {value}
      </span>
    </div>
  );
}

function Card({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="min-w-0 rounded-[12px] border-[0.5px] border-divider bg-surface px-4 py-3">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h3 className="m-0 flex-1 text-body font-semibold text-fg">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}

function Figure({ label, value, text }: { label: string; value?: number; text?: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-caption text-muted">{label}</span>
      <span className="font-display text-display font-bold text-fg">{text ?? compact(value ?? 0)}</span>
    </div>
  );
}

/** 横棒の一覧（単一系列なので凡例は不要）。 */
function Bars({ items }: { items: { label: string; value: number }[] }) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
      {items.map((i) => (
        <li key={i.label} className="grid grid-cols-[130px_minmax(0,1fr)_40px] items-center gap-2 text-footnote">
          <span className="truncate text-fg-2">{i.label}</span>
          <span className="h-3">
            <span
              className="block h-full rounded-r-[4px] bg-chart-1"
              style={{ width: `${(i.value / max) * 100}%`, minWidth: 2 }}
            />
          </span>
          <span className="text-right font-mono text-fg">{i.value}</span>
        </li>
      ))}
    </ul>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="m-0 py-6 text-center text-footnote text-muted">{children}</p>;
}

function PeriodPicker({ value, onChange }: { value: Period; onChange: (p: Period) => void }) {
  return (
    <Segmented
      label="期間"
      size="md"
      value={String(value)}
      options={PERIODS.map((p) => [String(p), `${p} 日`] as const)}
      onChange={(v) => onChange(Number(v) as Period)}
      className="shrink-0"
    />
  );
}
