import { describe, expect, it } from "vitest";
import { breadcrumb, childFolders, folderOptions, type FolderLike } from "@/lib/library/folders";

const f = (id: string, name: string, parent_id: string | null = null): FolderLike => ({ id, name, parent_id });
const tree = [f("b", "B 規程"), f("a", "A 議事録"), f("a1", "2024", "a"), f("a2", "2025", "a"), f("a1x", "4月", "a1")];

describe("folders", () => {
  it("直下のフォルダを名前順で返す", () => {
    expect(childFolders(tree, null).map((x) => x.id)).toEqual(["a", "b"]);
    expect(childFolders(tree, "a").map((x) => x.id)).toEqual(["a1", "a2"]);
    expect(childFolders(tree, "zzz")).toEqual([]);
  });

  it("パンくずはルートから順に並べ、見つからない ID は空にする", () => {
    expect(breadcrumb(tree, "a1x").map((x) => x.name)).toEqual(["A 議事録", "2024", "4月"]);
    expect(breadcrumb(tree, null)).toEqual([]);
    expect(breadcrumb(tree, "missing")).toEqual([]);
  });

  it("循環していても止まる", () => {
    const loop = [f("x", "x", "y"), f("y", "y", "x")];
    expect(breadcrumb(loop, "x").length).toBeLessThanOrEqual(2);
  });

  it("移動先の候補は木の順に深さつきで並べる", () => {
    expect(folderOptions(tree).map((o) => [o.id, o.depth])).toEqual([
      ["a", 0],
      ["a1", 1],
      ["a1x", 2],
      ["a2", 1],
      ["b", 0],
    ]);
  });
});
