"use client";

/** 技術者への報告（specs/028 R13〜R16）。左に一覧、行を押すと右（狭い幅では下）に詳細。読むだけで会話は続けない。 */
import createClient from "openapi-fetch";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AdminHeader } from "@/components/admin/admin-header";
import { StaticAnswer } from "@/components/chat/messages";
import { ToolSteps } from "@/components/chat/tool-steps";
import { useToast } from "@/components/feedback/toast-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { ListSkeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n/context";
import { reasonLabel, tagLabel } from "@/lib/admin/analytics";
import { afterStatusChange, diagnostics, statusLabel, type FeedbackDetail, type FeedbackRow } from "@/lib/admin/feedback";
import type { paths } from "@/lib/api/schema";
import { turnFromMessage } from "@/lib/chat/turn";
import { cn } from "@/lib/utils";

const client = createClient<paths>({ baseUrl: "/api" });

type Rating = "" | "up" | "down";
type Status = "" | "open" | "resolved";

const fmt = new Intl.DateTimeFormat("ja-JP", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function errorMessage(error: unknown, fallback: string): string {
  return (error as { error?: { message?: string } } | undefined)?.error?.message ?? fallback;
}

/** 利用者 ID → 表示名（メールアドレスは使わない）。取れなければ空。 */
function useMemberNames(): Record<string, string> {
  const [names, setNames] = useState<Record<string, string>>({});
  useEffect(() => {
    let alive = true;
    fetch("/api/admin/members")
      .then((r) => (r.ok ? r.json() : { items: [] }))
      .then((b: { items?: { id: string; name: string }[] }) => {
        if (alive) setNames(Object.fromEntries((b.items ?? []).map((u) => [u.id, u.name])));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);
  return names;
}

export function FeedbackView() {
  const { t } = useT();
  const a = t.admin;
  const push = useToast();
  const names = useMemberNames();
  const [rating, setRating] = useState<Rating>("down");
  const [status, setStatus] = useState<Status>("open");
  const [rows, setRows] = useState<FeedbackRow[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  // 未対応の「良くない」の件数（ナビに出す。状態を変えたらここで合わせる）
  const [openCount, setOpenCount] = useState<number | undefined>(undefined);
  // 絞り込みに合わなくなって一覧から外した行（状態を戻したら元の位置に戻す）
  const removed = useRef(new Map<string, { row: FeedbackRow; index: number }>());

  const fetchPage = useCallback(
    async (after: string | null) => {
      const { data, error: e } = await client.GET("/v1/admin/feedback", {
        params: { query: { rating: rating || undefined, status: status || undefined, cursor: after ?? undefined, limit: 50 } },
      });
      if (!data) throw new Error(errorMessage(e, a.loadFailed));
      return data;
    },
    [rating, status, a.loadFailed],
  );

  useEffect(() => {
    let alive = true;
    fetchPage(null).then(
      (p) => {
        if (!alive) return;
        removed.current.clear();
        setRows(p.items);
        setCursor(p.next_cursor ?? null);
        setOpenCount(p.open_count);
        setError(null);
      },
      (e: unknown) => {
        if (!alive) return;
        setRows([]);
        setError(e instanceof Error ? e.message : a.loadFailed);
      },
    );
    return () => {
      alive = false;
    };
  }, [fetchPage, a.loadFailed]);

  const more = async () => {
    if (!cursor) return;
    setLoadingMore(true);
    try {
      const p = await fetchPage(cursor);
      setRows((r) => [...(r ?? []), ...p.items]);
      setCursor(p.next_cursor ?? null);
    } catch (e) {
      push(e instanceof Error ? e.message : a.loadFailed, "error");
    } finally {
      setLoadingMore(false);
    }
  };

  return (
    <div className="grid h-dvh grid-cols-[minmax(0,1fr)] grid-rows-[auto_auto_1fr] bg-bg">
      <AdminHeader current="feedback" openFeedback={openCount} />
      <div className="border-b-[0.5px] border-divider px-[18px] py-2.5 max-md:px-3">
        <div className="mx-auto flex max-w-[1240px] flex-wrap items-center gap-2">
          <Select size="md" aria-label={t.chat.feedbackDownTitle} value={rating} onChange={(e) => setRating(e.target.value as Rating)}>
            <option value="">{a.filterAll}</option>
            <option value="down">{a.ratingDown}</option>
            <option value="up">{a.ratingUp}</option>
          </Select>
          <Select size="md" aria-label={a.status} value={status} onChange={(e) => setStatus(e.target.value as Status)}>
            <option value="">{a.filterAll}</option>
            <option value="open">{a.statusOpen}</option>
            <option value="resolved">{a.statusResolved}</option>
          </Select>
        </div>
      </div>

      <div className="min-h-0 overflow-y-auto md:overflow-hidden">
        <div className="mx-auto grid h-full max-w-[1240px] grid-cols-[minmax(0,380px)_minmax(0,1fr)] gap-4 px-[18px] py-4 max-md:grid-cols-[minmax(0,1fr)] max-md:px-2 max-md:py-2">
          <div className="min-h-0 overflow-y-auto rounded-card border-[0.5px] border-divider-strong bg-surface p-1.5 shadow-e1">
            {error && <p className="px-2 py-3 text-footnote text-danger">{error}</p>}
            {rows === null ? (
              <ListSkeleton />
            ) : rows.length === 0 && !error ? (
              <p className="py-16 text-center text-body text-muted">{a.empty}</p>
            ) : (
              rows.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => setSelected(r.id)}
                  aria-current={selected === r.id ? "true" : undefined}
                  className={cn(
                    "flex w-full flex-col gap-1 rounded-control border-0 bg-transparent px-2.5 py-2 text-left outline-none hover:bg-surface-2 focus-visible:ring-2 focus-visible:ring-accent/50",
                    selected === r.id && "bg-accent-soft hover:bg-accent-soft",
                  )}
                >
                  <span className="flex flex-wrap items-center gap-1.5">
                    <Badge tone={r.rating === "down" ? "danger" : "accent"}>{r.rating === "down" ? a.ratingDown : a.ratingUp}</Badge>
                    {r.reason_tags.map((g) => (
                      <Badge key={g}>{tagLabel(g)}</Badge>
                    ))}
                    <Badge tone={r.status === "open" ? "outline" : "neutral"}>{statusLabel(r.status)}</Badge>
                    <span className="ml-auto font-mono text-caption text-muted">{fmt.format(new Date(r.updated_at))}</span>
                  </span>
                  <span className="truncate text-footnote font-medium text-fg">{r.query}</span>
                  {r.comment && <span className="truncate text-caption text-fg-2">{r.comment}</span>}
                  <span className="flex flex-wrap gap-x-2 text-caption text-muted">
                    <span>{names[r.user_id] ?? "—"}</span>
                    {r.model_id && <span className="font-mono">{r.model_id}</span>}
                    {r.no_answer_reason && <span>{reasonLabel(r.no_answer_reason)}</span>}
                  </span>
                </button>
              ))
            )}
            {cursor && (
              <div className="flex justify-center py-2">
                <Button variant="secondary" size="sm" onClick={() => void more()} disabled={loadingMore}>
                  {loadingMore ? a.loading : a.loadMore}
                </Button>
              </div>
            )}
          </div>
          <div className="min-h-0 overflow-y-auto rounded-card border-[0.5px] border-divider-strong bg-surface shadow-e1">
            {selected ? (
              <FeedbackDetailPane
                key={selected}
                id={selected}
                names={names}
                onChanged={(d) => {
                  const next = afterStatusChange(rows ?? [], openCount ?? 0, d, status, removed.current);
                  setRows(next.rows);
                  setOpenCount(next.openCount);
                }}
              />
            ) : (
              <p className="py-16 text-center text-body text-muted">{a.selectHint}</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function FeedbackDetailPane({
  id,
  names,
  onChanged,
}: {
  id: string;
  names: Record<string, string>;
  onChanged: (d: FeedbackDetail) => void;
}) {
  const { t } = useT();
  const a = t.admin;
  const push = useToast();
  const [d, setD] = useState<FeedbackDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let alive = true;
    client.GET("/v1/admin/feedback/{feedback_id}", { params: { path: { feedback_id: id } } }).then(({ data, error }) => {
      if (!alive) return;
      if (!data) {
        push(errorMessage(error, a.loadFailed), "error");
        return;
      }
      setD(data);
      // 過程は最初から開いておく（システムの処理も見える。R14）
      setExpanded(Object.fromEntries(data.message.steps.map((s) => [s.id, true])));
    });
    return () => {
      alive = false;
    };
  }, [id, push, a.loadFailed]);

  const turn = useMemo(() => (d ? turnFromMessage(d.message, d.thread_id) : null), [d]);
  if (!d || !turn) return <ListSkeleton />;
  const reporter = names[d.user_id] ?? null;

  const setStatus = async (next: "resolve" | "reopen") => {
    setBusy(true);
    const path = next === "resolve" ? "/v1/admin/feedback/{feedback_id}/resolve" : "/v1/admin/feedback/{feedback_id}/reopen";
    const { data, error } = await client.POST(path, { params: { path: { feedback_id: id } } });
    setBusy(false);
    if (!data) {
      push(errorMessage(error, a.updateFailed), "error");
      return;
    }
    setD(data);
    onChanged(data);
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(diagnostics(d, reporter), null, 2));
      push(a.copied, "success");
    } catch {
      push(a.copyFailed, "error");
    }
  };

  const m = d.message;
  return (
    <div className="flex flex-col gap-5 p-4 max-md:p-3">
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone={d.rating === "down" ? "danger" : "accent"}>{d.rating === "down" ? a.ratingDown : a.ratingUp}</Badge>
            {d.reason_tags.map((g) => (
              <Badge key={g}>{tagLabel(g)}</Badge>
            ))}
            <Badge tone={d.status === "open" ? "outline" : "neutral"}>{statusLabel(d.status)}</Badge>
          </div>
          {d.comment && <p className="m-0 whitespace-pre-wrap break-words text-body text-fg">{d.comment}</p>}
          <p className="m-0 text-caption text-muted">
            {a.reporter}: {reporter ?? "—"} ・ {fmt.format(new Date(d.updated_at))} ・ {a.thread}: {d.thread_title}
          </p>
        </div>
        <div className="flex shrink-0 gap-1.5">
          {d.status === "open" ? (
            <Button variant="primary" size="sm" disabled={busy} onClick={() => void setStatus("resolve")}>
              {a.resolve}
            </Button>
          ) : (
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => void setStatus("reopen")}>
              {a.reopen}
            </Button>
          )}
          <Button variant="secondary" size="sm" onClick={() => void copy()}>
            {a.copyDiagnostics}
          </Button>
        </div>
      </div>

      <section className="flex flex-col gap-1.5">
        <h2 className="m-0 text-caption font-semibold text-muted">{a.question}</h2>
        <p className="m-0 whitespace-pre-wrap break-words text-body text-fg">{m.query}</p>
      </section>
      <section className="flex flex-col gap-1.5">
        <h2 className="m-0 text-caption font-semibold text-muted">{a.answer}</h2>
        <StaticAnswer text={turn.answer} onCite={() => {}} citationStyle="numbered" />
      </section>
      {turn.sources.length > 0 && (
        <section className="flex flex-col gap-1.5">
          <h2 className="m-0 text-caption font-semibold text-muted">{a.sources}</h2>
          <ol className="m-0 flex list-none flex-col gap-1 p-0">
            {turn.sources.map((s) => (
              <li key={s.id} className="text-footnote text-fg-2">
                <span className="font-medium text-fg">{s.title}</span>
                {s.sections.some((x) => x.heading) && (
                  <span className="text-muted"> — {s.sections.map((x) => x.heading).filter(Boolean).join(" / ")}</span>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}
      <section className="flex flex-col gap-1.5">
        <h2 className="m-0 text-caption font-semibold text-muted">{a.process}</h2>
        <div className="overflow-hidden rounded-card border-[0.5px] border-divider">
          <ToolSteps
            steps={turn.steps}
            variant="card"
            expandedMap={expanded}
            onToggleStep={(sid) => setExpanded((x) => ({ ...x, [sid]: !x[sid] }))}
            systemOpen
          />
        </div>
      </section>
      <section className="flex flex-col gap-1.5">
        <h2 className="m-0 text-caption font-semibold text-muted">{a.runInfo}</h2>
        <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-footnote">
          <dt className="text-muted">{a.model}</dt>
          <dd className="m-0 font-mono text-fg">{m.model_id ?? "—"}</dd>
          <dt className="text-muted">{a.duration}</dt>
          <dd className="m-0 font-mono text-fg">{(m.duration_ms / 1000).toFixed(1)} 秒</dd>
          <dt className="text-muted">{a.tokens}</dt>
          <dd className="m-0 font-mono text-fg">
            {m.tokens_in} + {m.tokens_out}
          </dd>
          <dt className="text-muted">{a.noAnswerReason}</dt>
          <dd className="m-0 text-fg">{m.no_answer_reason ? reasonLabel(m.no_answer_reason) : "—"}</dd>
        </dl>
      </section>
    </div>
  );
}
