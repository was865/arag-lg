import { describe, expect, it } from "vitest";
import type { KbInfo } from "@/hooks/use-kbs";
import { docStatus, formatBytes, filterStatuses, formatDate, uploadTarget, formatRows, formatSegments } from "@/lib/library/view";

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
  role: "editor",
  canManage: false,
  sharedWithEveryone: true,
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

describe("formatRows", () => {
  it("同じ形式をまとめ、多い順に並べる", () => {
    const rows = formatRows([
      { ext: "pdf", documents: 3, bytes: 30 },
      { ext: "docx", documents: 2, bytes: 20 },
      { ext: "doc", documents: 2, bytes: 5 },
      { ext: "zz", documents: 1, bytes: 1 },
    ]);
    expect(rows).toEqual([
      { label: "Word", documents: 4, bytes: 25 },
      { label: "PDF", documents: 3, bytes: 30 },
      { label: "ZZ", documents: 1, bytes: 1 },
    ]);
  });
  it("多すぎる形式は「その他」にまとめる", () => {
    const rows = formatRows(
      ["pdf", "md", "csv", "txt"].map((ext, i) => ({ ext, documents: 10 - i, bytes: 1 })),
      3,
    );
    expect(rows.map((r) => [r.label, r.documents])).toEqual([["PDF", 10], ["Markdown", 9], ["その他", 15]]);
  });
});

describe("formatSegments（形式の内訳の積み上げ棒）", () => {
  it("幅の合計は 100 で、少ない形式にも見える幅がある", () => {
    const segs = formatSegments([
      { label: "Markdown", documents: 11453, bytes: 0 },
      { label: "PDF", documents: 26, bytes: 0 },
      { label: "Word", documents: 5, bytes: 0 },
    ]);
    expect(Math.round(segs.reduce((a, s) => a + s.width, 0))).toBe(100);
    expect(segs[1].width).toBeGreaterThanOrEqual(2);
    expect(segs[0].width).toBeGreaterThan(90);
    expect(segs[1].color).not.toBe(segs[2].color);
  });
  it("文書が無ければ空", () => {
    expect(formatSegments([])).toEqual([]);
  });
});
