// SidebarRail 节点层测试：直接调用组件函数，遍历元素树验证结构与回调。
import { describe, expect, it, vi } from "vitest";
import * as React from "react";
import { collectElements } from "@/lib/test/element-tree";
import { SidebarRail, SidebarRailButton } from "./sidebar-rail";

/** aria-label で内側 button を探す（SidebarRailButton 展开後）。 */
function findButton(node: React.ReactNode, label: string) {
  return collectElements(
    node,
    (el) => el.type === "button" && (el.props as { ["aria-label"]?: string })["aria-label"] === label,
  )[0];
}

describe("SidebarRail（节点层测试）", () => {
  it("展开ボタンで onExpand、新建ボタンで onNew を呼ぶ", () => {
    const onExpand = vi.fn();
    const onNew = vi.fn();
    const node = SidebarRail({ onExpand, onNew, expandLabel: "展开侧栏", newLabel: "新建" });
    (findButton(node, "展开侧栏").props as { onClick?: () => void }).onClick?.();
    (findButton(node, "新建").props as { onClick?: () => void }).onClick?.();
    expect(onExpand).toHaveBeenCalledOnce();
    expect(onNew).toHaveBeenCalledOnce();
  });

  it("children の page 専属图标を描画し active を data-active に反映する", () => {
    const node = SidebarRail({
      onExpand: () => {},
      onNew: () => {},
      expandLabel: "展开",
      newLabel: "新建",
      children: <SidebarRailButton icon="clock" label="回交期" onClick={() => {}} active />,
    });
    const btn = findButton(node, "回交期");
    expect(btn).toBeDefined();
    expect((btn.props as Record<string, string>)["data-active"]).toBe("true");
  });

  it("新建ボタンは emphasis（text-fg）で強調し、展开ボタンは text-muted のまま", () => {
    const node = SidebarRail({ onExpand: () => {}, onNew: () => {}, expandLabel: "展开", newLabel: "新建" });
    const newCls = (findButton(node, "新建").props as { className?: string }).className ?? "";
    expect(newCls).toContain("text-fg");
    expect(newCls).not.toContain("text-muted");
    const expandCls = (findButton(node, "展开").props as { className?: string }).className ?? "";
    expect(expandCls).toContain("text-muted");
  });
});
