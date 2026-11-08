import { describe, expect, it } from "vitest";
import type { KbInfo } from "@/hooks/use-kbs";
import { docStatus, formatBytes, filterStatuses, formatDate, uploadTarget } from "@/lib/library/view";

const kb = (over: Partial<KbInfo>): KbInfo => ({
  id: "k",
  kind: "org",
  name: "社内規程",
  canWrite: true,
  teamId: null,
  documentCount: 0,
  status: "active",
  deletedAt: null,
  expiresAt: null,
  ...over,
});

describe("docStatus / filterStatuses", () => {
  it("状態を表示と絞り込みに写す", () => {
    expect(docStatus("ready").tone).toBe("ok");
    expect(docStatus("running")).toEqual({ label: "解析中", tone: "busy" });
    expect(docStatus("error").tone).toBe("danger");
    expect(filterStatuses("busy")).toBe("queued,running");
    expect(filterStatuses("error")).toBe("error,cancelled");
    expect(filterStatuses("all")).toBeNull();
  });
});

describe("uploadTarget", () => {
  const kbs = [
    kb({ id: "org", kind: "org", canWrite: false }),
    kb({ id: "arc", kind: "org", status: "archived" }),
    kb({ id: "me", kind: "personal", name: "" }),
    kb({ id: "team", kind: "org" }),
  ];
  it("開いている KB に書けるならそこ、書けなければ null", () => {
    expect(uploadTarget(kbs, "team")?.id).toBe("team");
    expect(uploadTarget(kbs, "org")).toBeNull();
    expect(uploadTarget(kbs, "arc")).toBeNull();
  });
  it("「すべて」では個人 KB、無ければ最初の書ける KB", () => {
    expect(uploadTarget(kbs, null)?.id).toBe("me");
    expect(uploadTarget(kbs.filter((k) => k.id !== "me"), null)?.id).toBe("team");
  });
});

describe("formatBytes / formatDate", () => {
  it("読みやすい単位にする", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatBytes(3.4 * 1024 ** 2)).toBe("3.4 MB");
    expect(formatBytes(1.25 * 1024 ** 3)).toBe("1.3 GB");
  });
  it("今年は月日だけ", () => {
    const now = new Date(2026, 10, 9);
    expect(formatDate(new Date(2026, 1, 3).toISOString(), now)).toBe("02/03");
    expect(formatDate(new Date(2025, 11, 31).toISOString(), now)).toBe("2025/12/31");
  });
});
