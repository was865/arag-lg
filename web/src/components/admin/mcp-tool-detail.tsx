"use client";

/**
 * 社内システムのツールの詳細と審査（specs/038 R15〜R17）。
 * 定義（指紋・入力の項目・サーバの説明の全文）・定義が変わったときの差分・直近の呼び出しを出し、
 * 副作用・モデルに渡す説明・使うを決めて、見ていた定義の指紋と一緒に送る（変わっていれば 409）。
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import { AdminHeader } from "@/components/admin/admin-header";
import { StatusBadge } from "@/components/admin/mcp-tools-view";
import { useToast } from "@/components/feedback/toast-provider";
import { Icon } from "@/components/icons";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CodeBlock } from "@/components/ui/code-block";
import { Field, Textarea } from "@/components/ui/input";
import { Segmented } from "@/components/ui/segmented";
import { ListSkeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { apiErrorMessage, mcpClient, useMcpAdmin } from "@/hooks/use-mcp-admin";
import type { components } from "@/lib/api/schema";
import { hasDiff, lineDiff, stableJson, type DiffLine } from "@/lib/admin/line-diff";
import { SIDE_EFFECT_LABEL, schemaParams, shortHash, type McpTool } from "@/lib/admin/mcp-tools";
import { formatLocalMinute } from "@/lib/datetime";
import { cn } from "@/lib/utils";

type Server = components["schemas"]["McpServerOut"];
type Stats = components["schemas"]["McpStatsOut"];
type SideEffect = "read" | "write";

export function McpToolDetail({ serverName, toolName }: { serverName: string; toolName: string }) {
  const { data, error, reload } = useMcpAdmin();
  const server = data?.servers.find((s) => s.name === serverName);
  const tool = server?.tools.find((t) => t.name === toolName);

  return (
    <div className="grid h-dvh grid-cols-[minmax(0,1fr)] grid-rows-[auto_1fr] bg-bg">
      <AdminHeader current="systems" />
      <div className="min-h-0 overflow-y-auto">
        <div className="mx-auto flex max-w-[1100px] flex-col gap-4 px-[18px] pb-12 pt-4 max-md:px-3">
          <nav aria-label="場所" className="flex items-center gap-1 text-caption text-muted">
            <Link href="/admin/systems" className="text-muted no-underline hover:text-fg">
              社内システム
            </Link>
            <Icon name="chevronRight" size={11} />
            <Link href="/admin/systems/tools" className="text-muted no-underline hover:text-fg">
              ツール
            </Link>
            {server && (
              <>
                <Icon name="chevronRight" size={11} />
                <Link
                  href={`/admin/systems/tools?server=${server.name}`}
                  className="text-muted no-underline hover:text-fg"
                >
                  {server.label}
                </Link>
              </>
            )}
          </nav>
          {error && <p className="m-0 text-footnote text-danger">{error}</p>}
          {!data && !error && <ListSkeleton rows={6} />}
          {data && (!server || !tool) && (
            <p className="m-0 text-footnote text-muted">
              ツールが見つかりません。システムから消えたか、名前が変わった可能性があります。
            </p>
          )}
          {server && tool && <Detail key={`${tool.def_hash}:${tool.approved_hash}`} server={server} tool={tool} onSaved={reload} />}
        </div>
      </div>
    </div>
  );
}

function Detail({ server, tool, onSaved }: { server: Server; tool: McpTool; onSaved: () => void }) {
  const params = schemaParams(tool.input_schema);
  return (
    <>
      <header className="flex flex-wrap items-center gap-2">
        <h1 className="m-0 font-mono text-title font-semibold text-fg">{tool.name}</h1>
        <StatusBadge status={tool.status} />
        {tool.usable ? <Badge>エージェントに渡す</Badge> : <Badge tone="outline">渡さない</Badge>}
        <span className="font-mono text-caption text-muted-2">
          {server.name}__{tool.name}
        </span>
      </header>
      {tool.status === "changed" && (
        <div
          role="alert"
          className="flex gap-2.5 rounded-card border-[0.5px] border-danger/40 bg-danger-soft px-4 py-3 text-footnote leading-[1.7] text-fg-2"
        >
          <span className="mt-0.5 text-danger">
            <Icon name="alert" size={15} />
          </span>
          <div>
            <b className="text-fg">審査の後に、サーバの側でこのツールの定義が変わりました。</b>
            審査し直すまで、エージェントには渡しません（「使う」の選択は残っています）。下の差分を確かめてから承認してください。
          </div>
        </div>
      )}
      <div className="grid grid-cols-[minmax(0,1fr)_340px] items-start gap-4 max-lg:grid-cols-1">
        <div className="flex min-w-0 flex-col gap-4">
          {tool.status === "changed" && <DiffCard tool={tool} />}
          <section className="card px-4 py-3.5">
            <h2 className="eyebrow m-0">サーバの説明</h2>
            <p className="m-0 mt-2 whitespace-pre-wrap break-words text-footnote leading-[1.7] text-fg">
              {tool.description || <span className="text-muted">（説明がありません）</span>}
            </p>
            <p className="m-0 mt-2 text-caption text-muted">
              サーバが返した文そのものです。指示に見える文（「これまでの指示を無視して…」など）が無いかを確かめてください。
            </p>
          </section>
          <section className="card px-4 py-3.5">
            <h2 className="eyebrow m-0">入力の項目</h2>
            {params.length === 0 ? (
              <p className="m-0 mt-2 text-footnote text-muted">項目はありません。</p>
            ) : (
              <table className="mt-2 w-full text-footnote">
                <thead className="text-left text-caption text-muted">
                  <tr>
                    <th className="py-1 font-medium">名前</th>
                    <th className="py-1 font-medium">型</th>
                    <th className="py-1 font-medium">必須</th>
                    <th className="py-1 font-medium">説明</th>
                  </tr>
                </thead>
                <tbody>
                  {params.map((p) => (
                    <tr key={p.name} className="border-t-[0.5px] border-divider align-top">
                      <td className="py-1.5 pr-3 font-mono text-fg">{p.name}</td>
                      <td className="py-1.5 pr-3 font-mono text-caption text-fg-2">{p.type}</td>
                      <td className="py-1.5 pr-3 text-fg-2">{p.required ? "必須" : "—"}</td>
                      <td className="py-1.5 text-fg-2">{p.description || <span className="text-muted-2">—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <CodeBlock className="mt-3" code={stableJson(tool.input_schema)} label="入力の型（JSON Schema）" maxHeight={200} />
          </section>
          <RecentCalls server={server} tool={tool} />
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          <ReviewCard server={server} tool={tool} onSaved={onSaved} />
          <section className="card px-4 py-3.5">
            <h2 className="eyebrow m-0">定義</h2>
            <dl className="m-0 mt-2 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-caption">
              <dt className="text-muted">今の指紋</dt>
              <dd className="m-0 break-all font-mono text-fg" title={tool.def_hash}>
                {shortHash(tool.def_hash, 16)}
              </dd>
              <dt className="text-muted">審査した指紋</dt>
              <dd
                className={cn("m-0 break-all font-mono", tool.status === "changed" ? "text-danger" : "text-fg")}
                title={tool.approved_hash ?? ""}
              >
                {shortHash(tool.approved_hash, 16)}
              </dd>
              <dt className="text-muted">審査した人</dt>
              <dd className="m-0 break-all text-fg-2">{tool.approved_by ?? "—"}</dd>
              <dt className="text-muted">審査した時刻</dt>
              <dd className="m-0 text-fg-2">{tool.approved_at ? formatLocalMinute(tool.approved_at) : "—"}</dd>
              <dt className="text-muted">取得した時刻</dt>
              <dd className="m-0 text-fg-2">{formatLocalMinute(tool.fetched_at)}</dd>
              <dt className="text-muted">サーバの申告</dt>
              <dd className="m-0 text-fg-2">{tool.read_only_hint ? "読み取り専用（readOnlyHint）" : "申告なし"}</dd>
            </dl>
            <p className="m-0 mt-2 text-caption leading-[1.6] text-muted">
              指紋は名前・説明・入力の型・読み取り専用の申告から作ります。取り直すたびに比べ、審査した指紋と違えば止めます。
            </p>
          </section>
        </div>
      </div>
    </>
  );
}

function DiffLines({ lines }: { lines: DiffLine[] }) {
  return (
    <pre className="card-sunken m-0 max-h-[280px] overflow-auto px-0 py-1.5 font-mono text-caption leading-[1.6]">
      {lines.map((l, i) => (
        <div
          key={i}
          className={cn(
            "whitespace-pre-wrap break-all px-3",
            l.kind === "add" && "bg-divider font-semibold text-fg",
            l.kind === "del" && "bg-danger-soft text-danger line-through decoration-danger/40",
            l.kind === "same" && "text-muted",
          )}
        >
          <span className="mr-2 select-none text-muted-2">{l.kind === "add" ? "+" : l.kind === "del" ? "−" : " "}</span>
          {l.text || " "}
        </div>
      ))}
    </pre>
  );
}

/** 審査した定義と今の定義の差分（R16）。 */
function DiffCard({ tool }: { tool: McpTool }) {
  const desc = lineDiff(tool.approved_description ?? "", tool.description);
  const schema = lineDiff(stableJson(tool.approved_input_schema), stableJson(tool.input_schema));
  const hintMoved = tool.approved_read_only !== null && tool.approved_read_only !== tool.read_only_hint;
  return (
    <section className="card px-4 py-3.5">
      <h2 className="eyebrow m-0">審査した定義からの差分</h2>
      <div className="mt-2 flex flex-col gap-3">
        {hintMoved && (
          <p className="m-0 text-footnote text-danger">
            読み取り専用の申告: {tool.approved_read_only ? "あり" : "なし"} → {tool.read_only_hint ? "あり" : "なし"}
          </p>
        )}
        <div>
          <h3 className="m-0 mb-1 text-caption font-medium text-fg-2">説明</h3>
          {hasDiff(desc) ? <DiffLines lines={desc} /> : <p className="m-0 text-caption text-muted">変わっていません。</p>}
        </div>
        <div>
          <h3 className="m-0 mb-1 text-caption font-medium text-fg-2">入力の型</h3>
          {hasDiff(schema) ? <DiffLines lines={schema} /> : <p className="m-0 text-caption text-muted">変わっていません。</p>}
        </div>
      </div>
    </section>
  );
}

/** 審査の欄（R7・R11・R17）。 */
function ReviewCard({ server, tool, onSaved }: { server: Server; tool: McpTool; onSaved: () => void }) {
  const push = useToast();
  const [side, setSide] = useState<SideEffect>(
    (tool.side_effect as SideEffect | null) ?? (tool.read_only_hint ? "read" : "write"),
  );
  const [text, setText] = useState(tool.model_description ?? "");
  const [enabled, setEnabled] = useState(tool.status === "unreviewed" ? side === "read" : tool.enabled);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const approved = tool.status === "approved";

  const submit = async () => {
    setBusy(true);
    setErr(null);
    const { error: e } = await mcpClient.POST("/v1/admin/mcp-servers/{server_id}/tools/review", {
      params: { path: { server_id: server.id } },
      body: {
        tool: tool.name,
        def_hash: tool.def_hash,
        side_effect: side,
        model_description: text.trim() || null,
        enabled: side === "read" && enabled,
      },
    });
    setBusy(false);
    if (e) {
      setErr(apiErrorMessage(e, "保存できませんでした"));
      return;
    }
    push(approved ? `${tool.name} を保存しました` : `${tool.name} の定義を承認しました`);
    onSaved();
  };

  return (
    <section className="card px-4 py-3.5">
      <h2 className="eyebrow m-0">審査</h2>
      <form
        className="mt-2 flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div className="flex flex-col gap-1.5">
          <span className="text-footnote font-medium text-fg-2">副作用</span>
          <Segmented<SideEffect>
            label="副作用"
            value={side}
            onChange={(v) => {
              setSide(v);
              if (v === "write") setEnabled(false);
            }}
            options={[
              ["read", SIDE_EFFECT_LABEL.read],
              ["write", SIDE_EFFECT_LABEL.write],
            ]}
            className="self-start"
          />
          {side === "read" && !tool.read_only_hint && (
            <p className="m-0 flex items-start gap-1 text-caption text-danger">
              <span className="mt-[2px] shrink-0">
                <Icon name="alert" size={11} />
              </span>
              サーバは読み取り専用と申告していません。書き込まないことを確かめてから「読み取り」にしてください。
            </p>
          )}
          {side === "write" && (
            <p className="m-0 text-caption text-muted">書き込みのツールはエージェントに渡しません。</p>
          )}
        </div>
        <Field label="モデルに渡す説明（任意）" hint="空ならサーバの説明をそのまま渡します。2,000 字まで。">
          <Textarea
            value={text}
            rows={5}
            maxLength={2000}
            placeholder={tool.description.split("\n")[0]}
            onChange={(e) => setText(e.target.value)}
          />
        </Field>
        <div className="flex items-center justify-between gap-3">
          <span className="text-footnote text-fg-2">エージェントに使わせる</span>
          <Switch label="使う" checked={side === "read" && enabled} disabled={side !== "read"} onChange={setEnabled} />
        </div>
        {err && <p className="m-0 text-footnote text-danger">{err}</p>}
        <Button type="submit" variant="primary" disabled={busy} className="self-end">
          {busy ? "保存しています…" : approved ? "保存" : "この定義を承認"}
        </Button>
      </form>
    </section>
  );
}

/** 直近の呼び出し（specs/033 R21 の数字から、このツールの分。R15）。 */
function RecentCalls({ server, tool }: { server: Server; tool: McpTool }) {
  const [data, setData] = useState<Stats | null>(null);
  useEffect(() => {
    let alive = true;
    void mcpClient
      .GET("/v1/admin/mcp-servers/{server_id}/stats", {
        params: { path: { server_id: server.id }, query: { hours: 24 * 7 } },
      })
      .then(({ data: d }) => {
        if (alive && d) setData(d);
      });
    return () => {
      alive = false;
    };
  }, [server.id]);
  const calls = (data?.recent ?? []).filter((c) => String(c.tool) === tool.name);
  return (
    <section className="card px-4 py-3.5">
      <h2 className="eyebrow m-0">直近の呼び出し（7 日）</h2>
      {!data ? (
        <ListSkeleton rows={2} />
      ) : calls.length === 0 ? (
        <p className="m-0 mt-2 text-footnote text-muted">このシステムの最近の呼び出しに、このツールはありません。</p>
      ) : (
        <ul className="m-0 mt-1 list-none p-0">
          {calls.map((c, i) => (
            <li key={i} className="flex items-baseline gap-2 border-t-[0.5px] border-divider py-1.5 text-caption first:border-t-0">
              <span className="shrink-0 font-mono text-muted">{formatLocalMinute(String(c.at))}</span>
              <span className={cn("shrink-0 tabular-nums", c.ok ? "text-muted" : "text-danger")}>
                {c.ok ? `${Number(c.ms).toLocaleString()} ms` : "失敗"}
              </span>
              <span className="min-w-0 truncate text-fg-2">{String(c.summary ?? "")}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
