import { describe, expect, it } from "vitest";
import { hasDiff, lineDiff, stableJson } from "@/lib/admin/line-diff";
import { filterRows, schemaParams, shortHash, sortRows, toolHref, type McpTool, type ToolRow } from "@/lib/admin/mcp-tools";

describe("lineDiff", () => {
  it("同じ行・消えた行・足した行に分ける", () => {
    expect(lineDiff("a\nb\nc", "a\nx\nc")).toEqual([
      { kind: "same", text: "a" },
      { kind: "del", text: "b" },
      { kind: "add", text: "x" },
      { kind: "same", text: "c" },
    ]);
  });
  it("空からの差分と、同じなら差分なし", () => {
    expect(lineDiff("", "a")).toEqual([{ kind: "add", text: "a" }]);
    expect(hasDiff(lineDiff("a\nb", "a\nb"))).toBe(false);
  });
  it("JSON はキーの順をそろえる", () => {
    expect(stableJson({ b: 1, a: { d: 1, c: 2 } })).toBe(stableJson({ a: { c: 2, d: 1 }, b: 1 }));
  });
});

const tool = (over: Partial<McpTool>): McpTool =>
  ({
    name: "get_stock",
    description: "在庫",
    read_only_hint: true,
    enabled: true,
    usable: true,
    input_schema: {},
    fetched_at: "2026-11-28T00:00:00Z",
    status: "approved",
    def_hash: "abcdef0123456789",
    side_effect: "read",
    model_description: null,
    approved_hash: "abcdef0123456789",
    approved_description: "在庫",
    approved_input_schema: {},
    approved_read_only: true,
    approved_by: "u",
    approved_at: "2026-11-28T00:00:00Z",
    ...over,
  }) as McpTool;

const row = (server: string, t: Partial<McpTool>): ToolRow => ({
  server: { id: server, name: server, label: server.toUpperCase(), enabled: true },
  tool: tool(t),
});

describe("ツールの一覧", () => {
  const rows = [
    row("erp", { name: "get_stock" }),
    row("erp", { name: "place_order", status: "unreviewed", usable: false }),
    row("cmms", { name: "list_equipment", status: "changed", usable: false, description: "設備の一覧" }),
  ];
  it("状態・システム・語で絞る", () => {
    expect(filterRows(rows, { q: "", status: "pending", server: "" }).map((r) => r.tool.name)).toEqual([
      "place_order",
      "list_equipment",
    ]);
    expect(filterRows(rows, { q: "", status: "usable", server: "" }).map((r) => r.tool.name)).toEqual(["get_stock"]);
    expect(filterRows(rows, { q: "設備", status: "all", server: "" })).toHaveLength(1);
    expect(filterRows(rows, { q: "", status: "all", server: "erp" })).toHaveLength(2);
  });
  it("変わった → 未審査 → 審査済みの順", () => {
    expect(sortRows(rows).map((r) => r.tool.status)).toEqual(["changed", "unreviewed", "approved"]);
  });
  it("指紋の頭と URL", () => {
    expect(shortHash("abcdef0123456789", 6)).toBe("abcdef");
    expect(shortHash(null)).toBe("—");
    expect(toolHref("erp", "a b")).toBe("/admin/systems/tools/erp/a%20b");
  });
});

describe("schemaParams", () => {
  it("項目・型・必須・説明", () => {
    const schema = {
      properties: {
        part: { type: "string", description: "部品番号" },
        status: { enum: ["open", "done"], title: "状態" },
        ids: { type: "array", items: { type: "integer" } },
        since: { anyOf: [{ type: "string" }, { type: "null" }] },
      },
      required: ["part"],
    };
    expect(schemaParams(schema)).toEqual([
      { name: "part", type: "string", required: true, description: "部品番号" },
      { name: "status", type: '"open" | "done"', required: false, description: "状態" },
      { name: "ids", type: "integer[]", required: false, description: "" },
      { name: "since", type: "string | null", required: false, description: "" },
    ]);
    expect(schemaParams(null)).toEqual([]);
  });
});
