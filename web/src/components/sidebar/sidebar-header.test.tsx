// SidebarHeader のノード単位テスト: コンポーネント関数を直接呼び、ブランド表示と折りたたみを確かめる。
import { describe, expect, it, vi } from "vitest";
import { collectElements, collectTexts } from "@/lib/test/element-tree";
import { SidebarHeader } from "./sidebar-header";

describe("SidebarHeader", () => {
  it("折りたたみボタンで onToggle を呼ぶ", () => {
    const onToggle = vi.fn();
    const node = SidebarHeader({ onToggle, closeLabel: "サイドバーを閉じる" });
    const btn = collectElements(
      node,
      (el) => el.type === "button" && (el.props as { title?: string }).title === "サイドバーを閉じる",
    )[0];
    (btn.props as { onClick?: () => void }).onClick?.();
    expect(onToggle).toHaveBeenCalledOnce();
  });

  it("ARag のブランドを出す", () => {
    const node = SidebarHeader({ onToggle: () => {}, closeLabel: "閉じる" });
    expect(collectTexts(node).some((t) => t === "ARag")).toBe(true);
  });
});
