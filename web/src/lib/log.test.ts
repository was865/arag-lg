import { describe, expect, it } from "vitest";
import { formatLog } from "@/lib/log";

describe("formatLog", () => {
  it("1 行の JSON に項目とエラーを入れる", () => {
    const o = JSON.parse(formatLog("error", "admin.audit_failed", { actor: "u1" }, new Error("boom")));
    expect(o).toMatchObject({ level: "error", logger: "web", event: "admin.audit_failed", actor: "u1", error: "boom", error_type: "Error" });
    expect(typeof o.ts).toBe("string");
  });
});
