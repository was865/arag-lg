import { describe, expect, it } from "vitest";
import { compareRows } from "@/lib/chat/compare";
import type { CitationMap, Source } from "@/lib/types";

const sources: Source[] = [
  { id: "d", type: "doc", title: "部品台帳（10月末）", sections: [{ id: "d1", heading: "部品", body: "" }] } as unknown as Source,
  {
    id: "s",
    type: "system",
    title: "ERP",
    sections: [
      {
        id: "s1",
        heading: "在庫",
        body: "",
        record: { system: "ERP", fetchedAt: "2026-11-18T10:32:00+09:00", columns: [], rows: [], total: 0 },
      },
    ],
  } as unknown as Source,
];
const map: CitationMap = { 1: { sourceId: "d", sectionId: "d1" }, 2: { sourceId: "s", sectionId: "s1" } };

describe("compareRows（specs/033 R20）", () => {
  it("同じ文の文書の数とシステムの数を並べる", () => {
    const rows = compareRows("軸受 6208ZZ の在庫は、台帳では 47 個[1]、今は 45 個[2]です。", map, sources);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      item: "軸受 6208ZZ の在庫",
      doc: { value: "47 個", n: 1, title: "部品台帳（10月末）" },
      system: { value: "45 個", n: 2, at: "2026-11-18T10:32:00+09:00" },
      same: false,
    });
  });
  it("片方の出典しか無い文・日付や番号だけの文は出さない", () => {
    expect(compareRows("在庫は 45 個です[2]。台帳は 10 月 31 日[1]時点。", map, sources)).toEqual([]);
    expect(compareRows("PO-2026-0436[2] と 2026-10-31[1]", map, sources)).toEqual([]);
  });
  it("単位が違えば比べない", () => {
    expect(compareRows("単価は 21,571 円[1]、在庫は 22 個[2]。", map, sources)).toEqual([]);
  });
  it("値の後ろの括弧の中の時点（「45個（2026年11月20日取得）」）は値にしない（3100 の試走）", () => {
    const rows = compareRows(
      "軸受 6208ZZ（P-5010）の在庫は、10月末の部品台帳では47個 [1] でしたが、現在は45個（2026年11月20日取得） [2] です。",
      map,
      sources,
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ item: "軸受 6208ZZ（P-5010）の在庫", doc: { value: "47 個" }, system: { value: "45 個" } });
  });
  it("同じ値なら same", () => {
    const rows = compareRows("発注点は 12[1]、ERP でも 12[2]。", map, sources);
    expect(rows[0].same).toBe(true);
  });
});
