import { describe, expect, it } from "vitest";
import { dirKey, isAccepted, planDirs, resolveFolders, splitRelPath } from "./folder-upload";

describe("フォルダごとのアップロード", () => {
  it("splitRelPath は親フォルダの並びを返し、隠しファイルは null", () => {
    expect(splitRelPath("規程/人事/就業規則.pdf")).toEqual(["規程", "人事"]);
    expect(splitRelPath("a.pdf")).toEqual([]);
    expect(splitRelPath("/規程//./a.pdf")).toEqual(["規程"]);
    expect(splitRelPath("規程/.DS_Store")).toBeNull();
    expect(splitRelPath("規程/.git/config.txt")).toBeNull();
  });

  it("isAccepted は拡張子で判定する（大文字も可）", () => {
    expect(isAccepted("A.PDF")).toBe(true);
    expect(isAccepted("memo.md")).toBe(true);
    expect(isAccepted("a.exe")).toBe(false);
    expect(isAccepted("noext")).toBe(false);
  });

  it("planDirs は途中のフォルダも含め、親が先に来る順で一度ずつ並べる", () => {
    expect(planDirs([["A", "B"], ["A"], ["C"], [], ["A", "B", "D"]]).map(dirKey)).toEqual([
      "A",
      "C",
      "A/B",
      "A/B/D",
    ]);
  });

  it("resolveFolders は既存の同名フォルダを使い、無いものだけ作る", async () => {
    const existing = [
      { id: "f-a", name: "A", parent_id: "base" },
      { id: "f-x", name: "B", parent_id: null }, // 別の親の B は使わない
    ];
    const created: [string, string | null][] = [];
    const map = await resolveFolders(
      "base",
      [["A"], ["A", "B"], ["C"]],
      existing,
      async (name, parent) => {
        created.push([name, parent]);
        return `new-${name}`;
      },
    );
    expect(created).toEqual([
      ["C", "base"],
      ["B", "f-a"],
    ]);
    expect(map.get("")).toBe("base");
    expect(map.get("A")).toBe("f-a");
    expect(map.get("A/B")).toBe("new-B");
    expect(map.get("C")).toBe("new-C");
  });
});
