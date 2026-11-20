"use client";
/**
 * 社内システム（MCP）の呼び出しの中身（specs/036）。技術者が確かめられるように、
 * 呼び出しの式 → 時間の内訳 → 切り替え（結果・問い合わせ・MCP・モデルに渡した文）の順に出す。既定は結果。
 */
import { useState } from "react";
import type { Dictionary } from "@/i18n/dictionary";
import { interpolate } from "@/i18n/interpolate";
import { callFromStep, callSignature, mcpRequest, mcpResponse, timing, type SystemCall } from "@/lib/chat/system-call";
import type { ToolCall } from "@/lib/types";
import { cn, formatMs } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { CodeBlock } from "@/components/ui/code-block";
import { Segmented } from "@/components/ui/segmented";
import { recordFromOutput, SystemRecordView } from "./system-record";
import { KeyValueGrid, boxCls } from "./shared";

type Tab = "result" | "queries" | "mcp" | "model";

/** `erp.list_suppliers(term="S-42")` を等幅で。サーバ名は淡く、ツール名を主に */
function Signature({ call, t }: { call: SystemCall; t: Dictionary }) {
  const sig = callSignature(call.server, call.tool, call.args);
  const args = sig.slice(call.server.length + call.tool.length + 2, -1);
  return (
    <CodeBlock code={sig} label="call" copyLabel={t.chat.copy} copiedLabel={t.chat.copied}>
      <span className="text-muted">{call.server}.</span>
      <span className="font-semibold text-fg">{call.tool}</span>
      <span className="text-muted">(</span>
      <span className="text-fg-2">{args}</span>
      <span className="text-muted">)</span>
    </CodeBlock>
  );
}

/** 往復の時間を、サーバの中と通信・整形に分けた細い帯と、問い合わせの回数などの札 */
function Timing({ call, t }: { call: SystemCall; t: Dictionary }) {
  const tm = timing(call);
  const chips: React.ReactNode[] = [];
  if (call.cached) chips.push(<Badge key="c" tone="outline">{t.chat.callCached}</Badge>);
  else if (call.queries.length || call.calls != null)
    chips.push(<Badge key="q">{interpolate(t.chat.callQueries, { n: String(call.queries.length || call.calls) })}</Badge>);
  if (call.erpUser) chips.push(<Badge key="u" mono={false} tone="neutral">{interpolate(t.chat.callErpUser, { user: call.erpUser })}</Badge>);
  if (call.traceId) chips.push(<span key="t" className="font-mono text-mini text-muted-2">{interpolate(t.chat.callTrace, { id: call.traceId })}</span>);
  if (!tm && chips.length === 0) return null;
  return (
    <div className="flex flex-col gap-1.5">
      {tm && (
        <div className="flex items-center gap-2.5 text-caption tabular-nums text-muted">
          <span className="font-mono text-fg-2">{interpolate(t.chat.callRtt, { ms: formatMs(tm.total) })}</span>
          <span aria-hidden className="flex h-1 min-w-12 max-w-48 flex-1 overflow-hidden rounded-full bg-divider">
            <span className="h-full bg-fg-2" style={{ width: `${tm.total ? (tm.server / tm.total) * 100 : 0}%` }} />
          </span>
          {call.serverMs != null && (
            <span className="flex items-center gap-1 font-mono">
              <span aria-hidden className="inline-block h-1.5 w-1.5 rounded-full bg-fg-2" />
              {interpolate(t.chat.callServer, { ms: formatMs(tm.server) })}
              <span aria-hidden className="ml-1.5 inline-block h-1.5 w-1.5 rounded-full bg-divider-strong" />
              {interpolate(t.chat.callRest, { ms: formatMs(tm.rest) })}
            </span>
          )}
        </div>
      )}
      {chips.length > 0 && <div className="flex flex-wrap items-center gap-1.5">{chips}</div>}
    </div>
  );
}

function Queries({ call, t }: { call: SystemCall; t: Dictionary }) {
  if (call.cached) return <div className={cn(boxCls, "text-muted")}>{t.chat.callCachedNote}</div>;
  if (call.queries.length === 0) return <div className={cn(boxCls, "text-muted")}>{t.chat.callNoQueries}</div>;
  // 1 行ずつの滝（時間の帯は最も長い問い合わせを基準に）。開くと文の全体とコピー
  const longest = Math.max(...call.queries.map((q) => q.ms ?? 0), 0);
  return (
    <div className="overflow-hidden rounded-control border-[0.5px] border-divider">
      <ol className="m-0 list-none p-0">
        {call.queries.map((q, i) => {
          const meta = [
            q.ms != null ? formatMs(q.ms) : null,
            q.rows != null ? interpolate(t.chat.callRows, { n: String(q.rows) }) : null,
          ].filter(Boolean);
          return (
            <li key={i} className="border-b-[0.5px] border-divider last:border-b-0">
              <details className="group/q">
                <summary className="grid cursor-pointer list-none grid-cols-[24px_auto_1fr_64px_auto] items-center gap-2.5 px-3 py-1.5 text-caption outline-none hover:bg-surface-2 focus-visible:ring-2 focus-visible:ring-accent/50 max-md:grid-cols-[24px_1fr_auto] [&::-webkit-details-marker]:hidden">
                  <span className="font-mono tabular-nums text-muted-2">#{i + 1}</span>
                  <span className="eyebrow font-mono max-md:hidden">
                    {t.chat.callLang[q.lang] ?? q.lang}
                  </span>
                  <span className="min-w-0 truncate font-mono text-fg-2 group-open/q:text-fg">{q.text}</span>
                  <span aria-hidden className="h-1 overflow-hidden rounded-full bg-divider max-md:hidden">
                    {q.ms != null && longest > 0 && (
                      <span className="block h-full rounded-full bg-fg-2" style={{ width: `${Math.max((q.ms / longest) * 100, 4)}%` }} />
                    )}
                  </span>
                  <span className="whitespace-nowrap text-right font-mono tabular-nums text-muted">{meta.join(" · ")}</span>
                </summary>
                <div className="px-3 pb-2.5">
                  <CodeBlock
                    code={q.text}
                    lang={q.lang}
                    label={t.chat.callLang[q.lang] ?? q.lang}
                    meta={[`#${i + 1}`, ...meta].join(" · ")}
                    copyLabel={t.chat.copy}
                    copiedLabel={t.chat.copied}
                    maxHeight={220}
                  />
                </div>
              </details>
            </li>
          );
        })}
      </ol>
      {call.queriesDropped > 0 && (
        <div className="border-t-[0.5px] border-divider px-3 py-1.5 text-caption text-muted">
          {interpolate(t.chat.callDropped, { n: String(call.queriesDropped) })}
        </div>
      )}
    </div>
  );
}

export function SystemCallView({ step, t }: { step: ToolCall; t: Dictionary }) {
  const [tab, setTab] = useState<Tab>("result");
  const call = callFromStep(step);
  const output = step.output ?? {};
  const record = recordFromOutput(output);
  if (!call) {
    // 何も分からない古い記録: 今までどおり引数と結果
    const args = Object.entries(step.input).filter(([, v]) => v !== "" && v != null);
    return (
      <div className="space-y-2">
        {args.length > 0 && <KeyValueGrid rows={args.map(([k, v]) => ({ k, v: String(v) }))} />}
        {record && <SystemRecordView record={record} t={t} />}
      </div>
    );
  }
  const options: [Tab, React.ReactNode][] = [["result", t.chat.callTabs.result]];
  if (call.queries.length > 0 || call.cached)
    options.push([
      "queries",
      <>
        {t.chat.callTabs.queries}
        <span className="font-mono text-mini tabular-nums text-muted">{call.queries.length}</span>
      </>,
    ]);
  options.push(["mcp", t.chat.callTabs.mcp]);
  if (call.modelText) options.push(["model", t.chat.callTabs.model]);
  const shown = options.some(([v]) => v === tab) ? tab : "result";

  return (
    <div className="flex min-w-0 flex-col gap-2.5">
      <Signature call={call} t={t} />
      <Timing call={call} t={t} />
      <Segmented label={t.chat.callTabsLabel} value={shown} options={options} onChange={setTab} className="self-start" />
      <div className="min-w-0">
        {shown === "result" &&
          (record ? (
            // ツールと引数は上の式に出したので重ねない
            <SystemRecordView record={{ ...record, tool: undefined, args: undefined }} t={t} />
          ) : (
            <div className={cn(boxCls, "whitespace-pre-wrap break-words")}>{call.modelText ?? "—"}</div>
          ))}
        {shown === "queries" && <Queries call={call} t={t} />}
        {shown === "mcp" && (
          <div className="flex flex-col gap-2">
            <CodeBlock
              code={JSON.stringify(mcpRequest(call), null, 2)}
              label={t.chat.callRequest}
              copyLabel={t.chat.copy}
              copiedLabel={t.chat.copied}
              maxHeight={200}
            />
            <CodeBlock
              code={JSON.stringify(mcpResponse(output), null, 2)}
              label={t.chat.callResponse}
              copyLabel={t.chat.copy}
              copiedLabel={t.chat.copied}
              maxHeight={260}
            />
          </div>
        )}
        {shown === "model" && call.modelText && (
          <div className="flex flex-col gap-1.5">
            <CodeBlock code={call.modelText} copyLabel={t.chat.copy} copiedLabel={t.chat.copied} maxHeight={300} />
            <div className="text-caption text-muted">{t.chat.callModelNote}</div>
          </div>
        )}
      </div>
    </div>
  );
}
