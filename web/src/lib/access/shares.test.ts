// 共有リストの見方（specs/024 R8・R11）
import { describe, expect, it } from "vitest";
import { accessLoss, effectiveRoles, reasonLabel, shareError, shareSummary, type Share } from "@/lib/access/shares";

const everyone: Share = { subject_type: "everyone", subject_id: "", role: "viewer" };
const mfg: Share = { subject_type: "department", subject_id: "mfg", role: "viewer" };
const qa: Share = { subject_type: "department", subject_id: "qa", role: "editor" };
const sato: Share = { subject_type: "user", subject_id: "sato", role: "manager" };
const members = { mfg: ["tanaka", "suzuki"], qa: ["tanaka", "ito"] };
const all = ["tanaka", "suzuki", "ito", "sato", "kato"];

describe("effectiveRoles", () => {
  it("1 人に複数の行が当たれば強い役割", () => {
    const r = effectiveRoles([mfg, qa, sato], members, all);
    expect(Object.fromEntries(r)).toEqual({ tanaka: "editor", suzuki: "viewer", ito: "editor", sato: "manager" });
  });
  it("全員は社内の全員", () => {
    expect(effectiveRoles([everyone, sato], members, all).size).toBe(5);
  });
});

describe("accessLoss", () => {
  it("部門を外すと、兼務で残る人は除いて見られなくなる人を出す", () => {
    expect(accessLoss([mfg, qa, sato], [qa, sato], members, all)).toEqual({ lost: ["suzuki"], lowered: [] });
  });
  it("全員を外す・役割を下げる", () => {
    const after: Share[] = [{ ...qa, role: "viewer" }, sato];
    expect(accessLoss([everyone, qa, sato], after, members, all)).toEqual({
      lost: ["kato", "suzuki"],
      lowered: ["ito", "tanaka"],
    });
  });
});

describe("shareSummary", () => {
  const name = (id: string) => ({ mfg: "製造部", qa: "品質保証部", hr: "人事部" })[id] ?? id;
  it("全員", () => expect(shareSummary([everyone, sato], name, 0)).toBe("社内の全員が閲覧"));
  it("部門は 2 つまで、残りは数で", () => {
    const hr: Share = { subject_type: "department", subject_id: "hr", role: "viewer" };
    expect(shareSummary([mfg, qa, hr, sato], name, 3)).toBe("製造部・品質保証部 ほか 2 件が利用 · 編集できる人 3 名");
  });
  it("人だけ", () => expect(shareSummary([sato], name, 1)).toBe("1 名が利用 · 編集できる人 1 名"));
});

describe("shareError", () => {
  it("全員に編集・管理が無い", () => {
    expect(shareError([{ ...everyone, role: "editor" }, sato])).toMatch(/全員には閲覧だけ/);
    expect(shareError([everyone])).toMatch(/管理できる人/);
    expect(shareError([everyone, sato])).toBeNull();
  });
});

describe("reasonLabel", () => {
  const name = (id: string) => (id === "d1" ? "製造部" : "?");
  it("経路ごとに言い分ける", () => {
    expect(reasonLabel({ subject_type: "everyone", subject_id: "", role: "viewer" }, name)).toBe("社内の全員として（閲覧）");
    expect(reasonLabel({ subject_type: "department", subject_id: "d1", role: "editor" }, name)).toBe(
      "製造部のメンバーとして（編集）",
    );
    expect(reasonLabel({ subject_type: "user", subject_id: "u1", role: "manager" }, name)).toBe("本人に付与（管理）");
  });
});
