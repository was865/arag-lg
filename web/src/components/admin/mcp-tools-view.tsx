"use client";

/**
 * 社内システムのツールの一覧（specs/038 R14）。すべてのシステムのツールを 1 つの表で出し、審査待ちを先に並べる。
 * 「使う」は審査済みで副作用が読み取りのときだけ切り替えられる。行のツール名から詳細（審査）へ移る。
 */
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { AdminHeader } from "@/components/admin/admin-header";
import { SystemsNav } from "@/components/admin/systems-nav";
import { useToast } from "@/components/feedback/toast-provider";
import { Icon } from "@/components/icons";
import { Badge } from "@/components/ui/badge";
import { SearchField, Select } from "@/components/ui/input";
import { Segmented } from "@/components/ui/segmented";
import { ListSkeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { apiErrorMessage, mcpClient, useMcpAdmin } from "@/hooks/use-mcp-admin";
import {
  SIDE_EFFECT_LABEL,
  filterRows,
  shortHash,
  sortRows,
  toolHref,
  toolRows,
  type ToolFilter,
  type ToolRow,
} from "@/lib/admin/mcp-tools";
import { cn } from "@/lib/utils";

type StatusFilter = ToolFilter["status"];

export function StatusBadge({ status }: { status: ToolRow["tool"]["status"] }) {
  if (status === "changed") return <Badge tone="danger">定義が変わった</Badge>;
  if (status === "unreviewed") return <Badge tone="outline">未審査</Badge>;
  return <Badge>審査済み</Badge>;
}

export function McpToolsView() {
  const push = useToast();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { data, error, reload } = useMcpAdmin();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const server = params.get("server") ?? "";
  const statusParam = params.get("status");
  const status: StatusFilter = statusParam === "pending" || statusParam === "usable" ? statusParam : "all";

  // 絞り込みは URL に置く（システムの行の「審査待ち」から開ける）
  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  const all = useMemo(() => toolRows(data?.servers ?? []), [data]);
  const rows = useMemo(() => sortRows(filterRows(all, { q, status, server })), [all, q, status, server]);
  const count = (s: StatusFilter) => filterRows(all, { q: "", status: s, server }).length;
  const pending = data?.servers.reduce((n, s) => n + s.pending_review, 0) ?? 0;

  const toggle = async (r: ToolRow, on: boolean) => {
    const srv = data?.servers.find((s) => s.id === r.server.id);
    if (!srv) return;
    const want = srv.tools.filter((t) => (t.name === r.tool.name ? on : t.enabled)).map((t) => t.name);
    setBusy(`${r.server.name}/${r.tool.name}`);
    const { error: e } = await mcpClient.PUT("/v1/admin/mcp-servers/{server_id}/tools", {
      params: { path: { server_id: srv.id } },
      body: { enabled: want },
    });
    setBusy(null);
    if (e) push(apiErrorMessage(e, "変更できませんでした"), "error");
    else push(`${r.tool.name} を${on ? "使う" : "使わない"}にしました`);
    reload();
  };

  return (
    <div className="grid h-dvh grid-cols-[minmax(0,1fr)] grid-rows-[auto_1fr] bg-bg">
      <AdminHeader current="systems" />
      <div className="min-h-0 overflow-y-auto">
        <div className="mx-auto flex max-w-[1100px] flex-col gap-4 px-[18px] pb-12 pt-4 max-md:px-3">
          <SystemsNav current="tools" pending={pending} />
          <div className="flex flex-wrap items-center gap-2">
            <SearchField
              placeholder="ツール・システム・説明で探す"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onClear={() => setQ("")}
              className="w-[280px] max-md:w-full"
            />
            <Segmented<StatusFilter>
              label="状態で絞る"
              value={status}
              onChange={(v) => setParam("status", v === "all" ? "" : v)}
              size="md"
              options={[
                ["all", `すべて ${count("all")}`],
                ["pending", `審査待ち ${count("pending")}`],
                ["usable", `使用中 ${count("usable")}`],
              ]}
            />
            <Select
              size="md"
              aria-label="システムで絞る"
              value={server}
              onChange={(e) => setParam("server", e.target.value)}
              className="w-auto"
            >
              <option value="">すべてのシステム</option>
              {data?.servers.map((s) => (
                <option key={s.id} value={s.name}>
                  {s.label}
                </option>
              ))}
            </Select>
          </div>
          {error && <p className="m-0 text-footnote text-danger">{error}</p>}
          {!data && !error && <ListSkeleton rows={6} />}
          {data && (
            <section className="card overflow-x-auto">
              <div className="px-4 pb-2 pt-3.5">
                <h2 className="m-0 text-callout font-semibold text-fg">ツール</h2>
                <p className="m-0 mt-0.5 text-caption leading-[1.6] text-muted">
                  サーバが返すツールの説明はモデルにそのまま入るので、1 つずつ審査してから使います。審査した定義は指紋で固定し、
                  サーバの側で変わったら審査し直すまでエージェントに渡しません。副作用はサーバの申告（readOnlyHint）ではなく、ここで決めます。
                </p>
              </div>
              {rows.length === 0 ? (
                <p className="m-0 border-t-[0.5px] border-divider px-4 py-5 text-footnote text-muted">
                  {all.length === 0 ? "ツールがありません。システムの「接続を確認」で読み込みます。" : "条件に合うツールはありません。"}
                </p>
              ) : (
                <table className="w-full min-w-[760px] table-fixed text-footnote">
                  <colgroup>
                    <col />
                    <col className="w-[120px]" />
                    <col className="w-[88px]" />
                    <col className="w-[120px]" />
                    <col className="w-[112px]" />
                    <col className="w-[72px]" />
                  </colgroup>
                  <thead className="text-left text-caption text-muted">
                    <tr className="border-t-[0.5px] border-divider">
                      <th className="py-1.5 pl-4 font-medium">ツール</th>
                      <th className="py-1.5 font-medium">状態</th>
                      <th className="py-1.5 font-medium">副作用</th>
                      <th className="py-1.5 font-medium">サーバの申告</th>
                      <th className="py-1.5 font-medium">定義の指紋</th>
                      <th className="py-1.5 pr-4 text-right font-medium">使う</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => {
                      const { tool: t } = r;
                      const key = `${r.server.name}/${t.name}`;
                      const canUse = t.status === "approved" && t.side_effect === "read";
                      return (
                        <tr key={key} className="border-t-[0.5px] border-divider align-top hover:bg-divider/40">
                          <td className="py-2 pl-4 pr-3">
                            <Link
                              href={toolHref(r.server.name, t.name)}
                              className="block truncate font-mono text-footnote font-semibold text-fg no-underline hover:underline"
                            >
                              {t.name}
                            </Link>
                            <div className="mt-0.5 flex min-w-0 items-center gap-1.5 text-caption text-muted">
                              <span className="shrink-0">{r.server.label}</span>
                              {t.model_description && <Badge tone="outline">説明を書き換え</Badge>}
                            </div>
                            <p className="m-0 mt-0.5 truncate text-caption text-fg-2" title={t.model_description ?? t.description}>
                              {(t.model_description ?? t.description).split("\n")[0]}
                            </p>
                          </td>
                          <td className="py-2 pr-3">
                            <StatusBadge status={t.status} />
                          </td>
                          <td className="py-2 pr-3 text-fg-2">
                            {t.side_effect ? (
                              <span className={cn(t.side_effect === "write" && "text-danger")}>
                                {SIDE_EFFECT_LABEL[t.side_effect]}
                              </span>
                            ) : (
                              <span className="text-muted-2">—</span>
                            )}
                          </td>
                          <td className="py-2 pr-3 text-muted">
                            {t.read_only_hint ? (
                              <span className="inline-flex items-center gap-1">
                                <Icon name="check" size={11} />
                                読み取り専用
                              </span>
                            ) : (
                              "申告なし"
                            )}
                          </td>
                          <td className="py-2 pr-3 font-mono text-caption text-muted" title={t.def_hash}>
                            {shortHash(t.def_hash)}
                          </td>
                          <td
                            className={cn("py-2 pr-4 text-right", t.enabled && !t.usable && "opacity-50")}
                            title={t.enabled && !t.usable ? "使うにしていますが、審査し直すまで渡していません" : undefined}
                          >
                            <Switch
                              label={`${t.name} を使う`}
                              checked={t.enabled}
                              disabled={busy === key || (!t.enabled && !canUse)}
                              onChange={(v) => void toggle(r, v)}
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
