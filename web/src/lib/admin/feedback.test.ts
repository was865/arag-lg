import { describe, expect, it } from "vitest";
import { diagnostics, statusLabel, type FeedbackDetail } from "@/lib/admin/feedback";

const detail: FeedbackDetail = {
  id: "f1",
  rating: "down",
  reason_tags: ["error"],
  comment: "数字が違う",
  status: "open",
  user_id: "u-secret-id",
  resolved_by: "admin-id",
  resolved_at: null,
  created_at: "2026-11-13T00:00:00Z",
  updated_at: "2026-11-13T00:00:00Z",
  thread_id: "t1",
  thread_title: "在庫",
  message: {
    id: "m1",
    ordinal: 1,
    query: "在庫は？",
    answer: "6 個 [1]",
    status: "completed",
    model_id: "gemma4-12b",
    tokens_in: 10,
    tokens_out: 5,
    duration_ms: 900,
    steps: [
      {
        id: "s1", name: "search", label: "検索", status: "done", duration_ms: 1, summary: "",
        input: { query: "在庫", api_key: "sk-live-xxx", headers: { Authorization: "Bearer t" } },
        output: { email: "alice@example.com", hits: 3 },
      },
    ],
    sources: [],
    citation_map: {},
    no_answer_reason: null,
    created_at: "2026-11-13T00:00:00Z",
    suggestions: [],
    feedback: null,
  },
} as unknown as FeedbackDetail;

describe("diagnostics（診断用にコピー、specs/028 R16）", () => {
  it("報告者は表示名だけにし、ID・メールアドレス・鍵は入れない", () => {
    const d = diagnostics(detail, "Alice");
    const text = JSON.stringify(d);
    expect(d.report_version).toBe(1);
    expect(d.feedback.reporter).toBe("Alice");
    for (const bad of ["u-secret-id", "admin-id", "alice@example.com", "sk-live-xxx", "Bearer t"]) expect(text).not.toContain(bad);
    const keys = new Set<string>();
    const walk = (v: unknown) => {
      if (Array.isArray(v)) v.forEach(walk);
      else if (v && typeof v === "object")
        for (const [k, x] of Object.entries(v)) {
          keys.add(k);
          walk(x);
        }
    };
    walk(d);
    for (const k of ["user_id", "resolved_by", "email", "api_key", "Authorization", "headers"]) expect(keys.has(k)).toBe(false);
    // 調べるのに要るものは入れる
    expect(d.message.query).toBe("在庫は？");
    expect(d.message.steps[0].input).toEqual({ query: "在庫" });
    expect(d.message.model_id).toBe("gemma4-12b");
  });

  it("状態の表示名", () => {
    expect(statusLabel("open")).toBe("未対応");
    expect(statusLabel("resolved")).toBe("対応済み");
  });
});
