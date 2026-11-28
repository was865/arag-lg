/** 社内システムのツールの管理画面の表示の整形（specs/038）。 */
import type { components } from "@/lib/api/schema";

type Server = components["schemas"]["McpServerOut"];
export type McpTool = components["schemas"]["McpToolOut"];
export type ToolStatus = McpTool["status"];

/** 一覧の 1 行（ツールと、それを出すシステム）。 */
export type ToolRow = { server: Pick<Server, "id" | "name" | "label" | "enabled">; tool: McpTool };

export const STATUS_LABEL: Record<ToolStatus, string> = {
  unreviewed: "未審査",
  approved: "審査済み",
  changed: "定義が変わった",
};

export const SIDE_EFFECT_LABEL = { read: "読み取り", write: "書き込み" } as const;

/** 指紋の頭（表示用）。 */
export function shortHash(h: string | null | undefined, n = 10): string {
  return h ? h.slice(0, n) : "—";
}

export function toolRows(servers: Server[]): ToolRow[] {
  return servers.flatMap((s) =>
    s.tools.map((tool) => ({ server: { id: s.id, name: s.name, label: s.label, enabled: s.enabled }, tool })),
  );
}

export type ToolFilter = { q: string; status: "all" | "pending" | "usable"; server: string };

export function filterRows(rows: ToolRow[], f: ToolFilter): ToolRow[] {
  const q = f.q.trim().toLowerCase();
  return rows.filter(({ server, tool }) => {
    if (f.server && server.name !== f.server) return false;
    if (f.status === "pending" && tool.status === "approved") return false;
    if (f.status === "usable" && !tool.usable) return false;
    if (!q) return true;
    const hay = `${tool.name} ${server.name} ${server.label} ${tool.description} ${tool.model_description ?? ""}`;
    return hay.toLowerCase().includes(q);
  });
}

/** 審査待ちを先に、そのあとシステム・名前の順。 */
export function sortRows(rows: ToolRow[]): ToolRow[] {
  const rank = (t: McpTool) => (t.status === "changed" ? 0 : t.status === "unreviewed" ? 1 : 2);
  return [...rows].sort(
    (a, b) =>
      rank(a.tool) - rank(b.tool) ||
      a.server.name.localeCompare(b.server.name) ||
      a.tool.name.localeCompare(b.tool.name),
  );
}

export type Param = { name: string; type: string; required: boolean; description: string };

/** 入力の型（JSON Schema）の項目の表（R15）。 */
export function schemaParams(schema: Record<string, unknown> | null | undefined): Param[] {
  const props = (schema?.properties ?? {}) as Record<string, Record<string, unknown>>;
  const required = new Set(Array.isArray(schema?.required) ? (schema.required as string[]) : []);
  return Object.entries(props).map(([name, p]) => ({
    name,
    type: typeOf(p),
    required: required.has(name),
    description: typeof p.description === "string" ? p.description : typeof p.title === "string" ? p.title : "",
  }));
}

function typeOf(p: Record<string, unknown>): string {
  if (Array.isArray(p.enum)) return p.enum.map((v) => JSON.stringify(v)).join(" | ");
  if (typeof p.type === "string") return p.type === "array" && p.items ? `${typeOf(p.items as Record<string, unknown>)}[]` : p.type;
  if (Array.isArray(p.type)) return p.type.join(" | ");
  const alt = (p.anyOf ?? p.oneOf) as Record<string, unknown>[] | undefined;
  if (Array.isArray(alt)) return alt.map(typeOf).join(" | ");
  return "—";
}

/** ツールの詳細の URL。 */
export function toolHref(server: string, tool: string): string {
  return `/admin/systems/tools/${encodeURIComponent(server)}/${encodeURIComponent(tool)}`;
}
