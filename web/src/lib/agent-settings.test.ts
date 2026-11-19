import { describe, expect, it } from "vitest";
import { AGENT_DEFAULTS, AGENT_FIELDS, agentCfgPayload, changedCount, clampAgentCfg } from "./agent-settings";

describe("回答の設定", () => {
  it("clampAgentCfg は API と同じ範囲に丸め、型違いは既定に戻す", () => {
    const c = clampAgentCfg({ top_k: 99, max_steps: 1, per_document: -3, grade_threshold: 2, require_citations: "x" });
    expect(c.top_k).toBe(20);
    expect(c.max_steps).toBe(5);
    expect(c.per_document).toBe(0);
    expect(c.grade_threshold).toBe(1);
    expect(c.require_citations).toBe(true);
    expect(clampAgentCfg(null)).toEqual(AGENT_DEFAULTS);
    expect(clampAgentCfg({ top_k: 7.6 }).top_k).toBe(8);
  });

  it("続けて聞くは既定でオン、型違いは既定に戻し、オフにしたときだけ送る（specs/028 R7）", () => {
    expect(AGENT_DEFAULTS.followups).toBe(true);
    expect(clampAgentCfg({ followups: "no" }).followups).toBe(true);
    expect(clampAgentCfg({ followups: false }).followups).toBe(false);
    expect(agentCfgPayload({ ...AGENT_DEFAULTS, followups: false })).toEqual({ followups: false });
    expect(AGENT_FIELDS.find((f) => f.key === "followups")).toMatchObject({ kind: "bool" });
  });

  it("社内システムは既定でオン、オフにしたときだけ送る（specs/032 R11）", () => {
    expect(AGENT_DEFAULTS.use_systems).toBe(true);
    expect(clampAgentCfg({ use_systems: 1 }).use_systems).toBe(true);
    expect(agentCfgPayload({ ...AGENT_DEFAULTS, use_systems: false })).toEqual({ use_systems: false });
    expect(AGENT_FIELDS.find((f) => f.key === "use_systems")).toMatchObject({ kind: "bool", label: "社内システムも調べる" });
  });

  it("候補の数は資料の数より小さくならない", () => {
    expect(clampAgentCfg({ top_k: 12, candidate_k: 5 }).candidate_k).toBe(12);
  });

  it("agentCfgPayload は既定から変えた項目だけ、無ければ null", () => {
    expect(agentCfgPayload(AGENT_DEFAULTS)).toBeNull();
    expect(agentCfgPayload({ ...AGENT_DEFAULTS, top_k: 10, admit_unknown: false })).toEqual({
      top_k: 10,
      admit_unknown: false,
    });
    expect(changedCount({ ...AGENT_DEFAULTS, top_k: 10 })).toBe(1);
  });

  it("画面に出す項目は既定値の範囲内にある", () => {
    for (const f of AGENT_FIELDS) {
      const d = AGENT_DEFAULTS[f.key];
      if (f.kind === "number") expect(d as number).toBeGreaterThanOrEqual(f.min);
      if (f.kind === "number") expect(d as number).toBeLessThanOrEqual(f.max);
    }
    expect(AGENT_FIELDS.some((f) => (f.key as string) === "verify")).toBe(false);
  });

  it("すべての項目に技術者向けの用語と説明がある", () => {
    for (const f of AGENT_FIELDS) {
      expect(f.term, f.key).toMatch(/\S/);
      expect(f.hint, f.key).toMatch(/\S/);
    }
  });
});
