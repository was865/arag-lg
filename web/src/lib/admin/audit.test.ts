import { describe, expect, it } from "vitest";
import { actionLabel, describeTarget, toRangeQuery } from "@/lib/admin/audit";

describe("actionLabel", () => {
  it("既知の操作は日本語、未知はそのまま", () => {
    expect(actionLabel("document.delete")).toBe("文書をごみ箱へ");
    expect(actionLabel("member.ban")).toBe("メンバーを停止");
    expect(actionLabel("x.y")).toBe("x.y");
  });
});

describe("describeTarget", () => {
  it("詳細のメール・公開範囲・役割を添える", () => {
    expect(describeTarget({ resource_type: "user", resource_id: "u1", detail: { email: "a@x", from: "member", to: "admin" } })).toBe(
      "a@x（メンバー → 管理者）",
    );
    expect(describeTarget({ resource_type: "thread", resource_id: "t1", detail: { visibility: "public" } })).toBe(
      "thread t1（リンクを知っている人）",
    );
    expect(describeTarget({ resource_type: null, resource_id: null, detail: null })).toBe("—");
  });
});

describe("toRangeQuery", () => {
  it("日付（その日の 0 時〜翌日 0 時、ローカル時刻）を ISO にする", () => {
    const q = toRangeQuery("2026-11-01", "2026-11-09");
    expect(new Date(q.from!).getDate()).toBe(1);
    expect(new Date(q.to!).getDate()).toBe(10);
    expect(toRangeQuery("", "")).toEqual({ from: undefined, to: undefined });
  });
});
