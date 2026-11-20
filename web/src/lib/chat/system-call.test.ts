import { describe, expect, it } from "vitest";
import { callFromStep, callSignature, codeTokens, mcpRequest, mcpResponse, timing } from "@/lib/chat/system-call";
import type { ToolCall } from "@/lib/types";

const step = (output: Record<string, unknown> | null, rawName = "erp__list_suppliers"): ToolCall => ({
  id: "c1",
  name: "system_query",
  rawName,
  label: "社内システム: ERP（Odoo）",
  status: "done",
  durationMs: 60,
  input: { term: "S-42" },
  output,
  summary: "",
});

const out = {
  server: "erp",
  tool: "list_suppliers",
  args: { term: "S-42" },
  rtt_ms: 52,
  system: "ERP（Odoo）",
  columns: ["仕入先コード", "仕入先名"],
  rows: [["S-42", "有限会社富士興産"]],
  total: 1,
  result: '<資料 n="16">\n| 仕入先コード |\n</資料>',
  trace: {
    id: "t1",
    ms: 29,
    calls: 2,
    cached: false,
    backend: "odoo",
    erp_user: "erp-viewer",
    queries: [
      { lang: "odoo", text: "res.partner.search_read([['ref', 'ilike', 'S-42']])", ms: 10.9, rows: 1 },
      { lang: "odoo", text: "product.supplierinfo.search_read([['partner_id', 'in', [35]]])", ms: 11, rows: 23 },
    ],
  },
};

describe("callFromStep", () => {
  it("段階の出力から呼び出しの中身を取り出す（specs/036）", () => {
    const c = callFromStep(step(out))!;
    expect(c.server).toBe("erp");
    expect(c.tool).toBe("list_suppliers");
    expect(c.args).toEqual({ term: "S-42" });
    expect(c.rttMs).toBe(52);
    expect(c.serverMs).toBe(29);
    expect(c.queryMs).toBeCloseTo(21.9);
    expect(c.queries).toHaveLength(2);
    expect(c.erpUser).toBe("erp-viewer");
    expect(c.modelText).toContain("<資料");
  });

  it("古い記録（server・tool が無い）はステップ名と入力から作る", () => {
    const c = callFromStep(step({ system: "ERP", columns: [], rows: [], total: 0 }))!;
    expect(c.server).toBe("erp");
    expect(c.tool).toBe("list_suppliers");
    expect(c.args).toEqual({ term: "S-42" });
    expect(c.rttMs).toBeNull();
    expect(c.queries).toEqual([]);
  });
});

describe("callSignature", () => {
  it("空の引数を除き、値は JSON の形で書く", () => {
    expect(callSignature("erp", "list_below_reorder", { without_orders: true, cursor: "", limit: null })).toBe(
      "erp.list_below_reorder(without_orders=true)",
    );
    expect(callSignature("cmms", "list_work_records", { equipment: "PM-04" })).toBe('cmms.list_work_records(equipment="PM-04")');
  });
});

describe("timing", () => {
  it("往復をサーバの中と通信・整形に分ける", () => {
    expect(timing({ rttMs: 52, serverMs: 29 })).toEqual({ total: 52, server: 29, rest: 23 });
    // サーバの時計の方が長いことがある（丸め）。往復を超えない
    expect(timing({ rttMs: 10, serverMs: 12 })).toEqual({ total: 10, server: 10, rest: 0 });
    expect(timing({ rttMs: null, serverMs: 5 })).toBeNull();
  });
});

describe("mcp", () => {
  it("JSON-RPC の要求を組み立て、応答は行と文を除いて見せる", () => {
    const c = callFromStep(step(out))!;
    expect(mcpRequest(c)).toEqual({
      jsonrpc: "2.0",
      method: "tools/call",
      params: { name: "list_suppliers", arguments: { term: "S-42" } },
    });
    const r = mcpResponse(step(out).output!);
    expect(r).not.toHaveProperty("result");
    expect(r.rows).toBe("[1 行]");
    expect((r.trace as Record<string, unknown>).queries).toBe("[2 件]");
  });
});

describe("codeTokens", () => {
  it("SQL のキーワード・文字列・数を分ける", () => {
    const toks = codeTokens("sql", "SELECT * FROM parts WHERE part_no = 'P-1' LIMIT 5");
    expect(toks.filter((t) => t.k === "kw").map((t) => t.t)).toEqual(["SELECT", "FROM", "WHERE", "LIMIT"]);
    expect(toks.find((t) => t.k === "str")?.t).toBe("'P-1'");
    expect(toks.find((t) => t.k === "num")?.t).toBe("5");
    expect(toks.map((t) => t.t).join("")).toBe("SELECT * FROM parts WHERE part_no = 'P-1' LIMIT 5");
  });
  it("Odoo はモデルとメソッドを分ける", () => {
    const toks = codeTokens("odoo", "res.partner.search_read([['ref', '=', 'S-1']], limit=80)");
    expect(toks[0]).toEqual({ t: "res.partner", k: "name" });
    expect(toks[1]).toEqual({ t: ".search_read", k: "kw" });
    expect(toks.map((t) => t.t).join("")).toBe("res.partner.search_read([['ref', '=', 'S-1']], limit=80)");
  });
});
