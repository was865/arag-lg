// SidebarNewButton 节点层测试：直接调用组件函数，遍历返回的元素树验证结构。
import { describe, expect, it, vi } from "vitest";
import { collectElements, collectTexts } from "@/lib/test/element-tree";
import { SidebarNewButton } from "./sidebar-new-button";

describe("SidebarNewButton（节点层测试）", () => {
  it("点击触发 onClick", () => {
    const onClick = vi.fn();
    const node = SidebarNewButton({ label: "新建测算", onClick });
    expect(node.type).toBe("button");
    (node.props as { onClick?: () => void }).onClick?.();
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("显示 label 文本", () => {
    const node = SidebarNewButton({ label: "新建测算", onClick: () => {} });
    expect(collectTexts(node).some((t) => t.includes("新建测算"))).toBe(true);
  });

  it("传 shortcut 时渲染 kbd 徽标", () => {
    const node = SidebarNewButton({ label: "新对话", onClick: () => {}, shortcut: "⌘N" });
    const kbds = collectElements(node, (el) => el.type === "kbd");
    expect(kbds).toHaveLength(1);
    expect(collectTexts(node).some((t) => t.includes("⌘N"))).toBe(true);
  });

  it("不传 shortcut 时无 kbd", () => {
    const node = SidebarNewButton({ label: "新对话", onClick: () => {} });
    expect(collectElements(node, (el) => el.type === "kbd")).toHaveLength(0);
  });
});
