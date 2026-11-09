"use client";

/** 監査ログ（specs/011-audit-log R5）。 */
import createClient from "openapi-fetch";
import { useEffect, useState } from "react";
import { AdminHeader } from "@/components/admin/admin-header";
import { Icon } from "@/components/icons";
import type { components, paths } from "@/lib/api/schema";
import { ACTION_GROUPS, actionLabel, describeTarget, toRangeQuery } from "@/lib/admin/audit";
import { cn } from "@/lib/utils";

type Row = components["schemas"]["AuditOut"];
const client = createClient<paths>({ baseUrl: "/api" });

interface Filters {
  action: string;
  actor: string;
  from: string;
  to: string;
}

async function fetchPage(f: Filters, cursor: string | null) {
  const range = toRangeQuery(f.from, f.to);
  const { data, error } = await client.GET("/v1/admin/audit", {
    params: {
      query: {
        action: f.action || undefined,
        actor: f.actor || undefined,
        from: range.from,
        to: range.to,
        cursor: cursor ?? undefined,
        limit: 50,
      },
    },
  });
  if (!data) {
    const msg = (error as { error?: { message?: string } } | undefined)?.error?.message;
    throw new Error(msg ?? "監査ログを取得できませんでした");
  }
  return data;
}

const fmt = new Intl.DateTimeFormat("ja-JP", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

export function AuditView() {
  const [filters, setFilters] = useState<Filters>({ action: "", actor: "", from: "", to: "" });
  const [actorInput, setActorInput] = useState("");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => setFilters((f) => ({ ...f, actor: actorInput.trim() })), 300);
    return () => window.clearTimeout(t);
  }, [actorInput]);

  useEffect(() => {
    let alive = true;
    fetchPage(filters, null).then(
      (p) => {
        if (!alive) return;
        setRows(p.items);
        setCursor(p.next_cursor);
        setError(null);
      },
      (e: unknown) => {
        if (!alive) return;
        setRows([]);
        setError(e instanceof Error ? e.message : "監査ログを取得できませんでした");
      },
    );
    return () => {
      alive = false;
    };
  }, [filters]);

  const more = async () => {
    if (!cursor) return;
    setLoadingMore(true);
    try {
      const p = await fetchPage(filters, cursor);
      setRows((r) => [...(r ?? []), ...p.items]);
      setCursor(p.next_cursor);
    } catch (e) {
      setError(e instanceof Error ? e.message : "続きを読み込めませんでした");
    } finally {
      setLoadingMore(false);
    }
  };

  const input =
    "h-8 rounded-lg border-[0.5px] border-divider-strong bg-surface px-2.5 text-[12.5px] text-fg outline-none focus:border-accent";
  return (
    <div className="grid h-dvh grid-cols-[minmax(0,1fr)] grid-rows-[auto_auto_1fr] bg-bg">
      <AdminHeader current="audit" />
      <div className="border-b-[0.5px] border-divider px-[18px] py-2.5 max-md:px-3">
        <div className="mx-auto flex max-w-[1100px] flex-wrap items-center gap-2">
          <select
            aria-label="操作の種類"
            value={filters.action}
            onChange={(e) => setFilters((f) => ({ ...f, action: e.target.value }))}
            className={input}
          >
            {ACTION_GROUPS.map((g) => (
              <option key={g.value} value={g.value}>
                {g.label}
              </option>
            ))}
          </select>
          <label className={cn(input, "flex min-w-[200px] flex-1 items-center gap-2 text-muted")}>
            <Icon name="search" size={13} />
            <input
              value={actorInput}
              onChange={(e) => setActorInput(e.target.value)}
              placeholder="操作した人（メール・ID）"
              className="min-w-0 flex-1 border-0 bg-transparent text-fg outline-none placeholder:text-muted-2"
            />
          </label>
          <input
            type="date"
            aria-label="開始日"
            value={filters.from}
            onChange={(e) => setFilters((f) => ({ ...f, from: e.target.value }))}
            className={input}
          />
          <span className="text-[12px] text-muted">〜</span>
          <input
            type="date"
            aria-label="終了日"
            value={filters.to}
            onChange={(e) => setFilters((f) => ({ ...f, to: e.target.value }))}
            className={input}
          />
        </div>
      </div>

      <div className="min-h-0 overflow-y-auto">
        <div className="mx-auto max-w-[1100px] px-[18px] pb-10 pt-2 max-md:px-2">
          <div className="grid grid-cols-[150px_200px_170px_minmax(0,1fr)_60px] gap-3 border-b-[0.5px] border-divider px-2 py-2 text-[10.5px] font-semibold uppercase tracking-[0.05em] text-muted-2 max-md:hidden">
            <span>日時</span>
            <span>操作した人</span>
            <span>操作</span>
            <span>対象</span>
            <span>結果</span>
          </div>
          {error && <p className="px-2 py-3 text-[12.5px] text-danger">{error}</p>}
          {rows === null ? (
            <div className="grid h-40 place-items-center">
              <span className="h-6 w-6 animate-[ar-spin_0.8s_linear_infinite] rounded-full border-2 border-divider-strong border-t-accent" />
            </div>
          ) : rows.length === 0 && !error ? (
            <p className="py-16 text-center text-[13px] text-muted">条件に合う記録はありません</p>
          ) : (
            rows.map((r) => (
              <div key={r.id} className="rounded-lg hover:bg-surface-2">
                <button
                  onClick={() => setOpen((x) => (x === r.id ? null : r.id))}
                  aria-expanded={open === r.id}
                  className="grid w-full grid-cols-[150px_200px_170px_minmax(0,1fr)_60px] items-center gap-3 px-2 py-2 text-left text-[12.5px] max-md:grid-cols-[minmax(0,1fr)_auto] max-md:gap-1"
                >
                  <span className="font-mono text-[11.5px] text-muted max-md:order-2">{fmt.format(new Date(r.ts))}</span>
                  <span className="truncate text-fg-2 max-md:order-3 max-md:col-span-2 max-md:text-[11.5px]">
                    {r.actor_email ?? r.actor_id ?? "システム"}
                  </span>
                  <span className="truncate font-medium text-fg max-md:order-1">{actionLabel(r.action)}</span>
                  <span className="truncate text-fg-2 max-md:order-4 max-md:col-span-2 max-md:text-[11.5px]">
                    {describeTarget(r)}
                  </span>
                  <span
                    className={cn(
                      "text-[11.5px] max-md:hidden",
                      r.result === "ok" ? "text-muted" : "text-danger",
                    )}
                  >
                    {r.result === "ok" ? "成功" : r.result === "denied" ? "拒否" : r.result}
                  </span>
                </button>
                {open === r.id && (
                  <dl className="m-0 grid grid-cols-[110px_minmax(0,1fr)] gap-x-3 gap-y-1 px-4 pb-3 text-[11.5px]">
                    {(
                      [
                        ["操作", r.action],
                        ["操作した人の ID", r.actor_id],
                        ["対象", [r.resource_type, r.resource_id].filter(Boolean).join(" ")],
                        ["IP", r.ip],
                        ["詳細", r.detail ? JSON.stringify(r.detail) : null],
                      ] as const
                    ).map(([k, v]) => (
                      <div key={k} className="contents">
                        <dt className="text-muted">{k}</dt>
                        <dd className="m-0 break-all font-mono text-fg-2">{v || "—"}</dd>
                      </div>
                    ))}
                  </dl>
                )}
              </div>
            ))
          )}
          {cursor && (
            <div className="flex justify-center pt-3">
              <button
                onClick={() => void more()}
                disabled={loadingMore}
                className="h-8 rounded-lg border-[0.5px] border-divider-strong px-3.5 text-[12.5px] font-medium text-fg hover:bg-divider disabled:opacity-60"
              >
                {loadingMore ? "読み込み中…" : "さらに読み込む"}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
