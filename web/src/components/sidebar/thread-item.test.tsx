// ThreadItem 节点层测试：验证共享 ThreadRow/ThreadMenuItems 的结构与文案注入。
// メニュー本体は Radix（ui/menu）なので、項目の構成は hook を持たない ThreadMenuItems で確かめる。
import { describe, it, expect, vi } from "vitest";
import * as React from "react";
import { ThreadRow, ThreadMenuItems } from "@/components/sidebar/thread-item";
import { MenuItem } from "@/components/ui/menu";
import { collectElements } from "@/lib/test/element-tree";
import type { ThreadSummary } from "@/lib/types";

const THREAD: ThreadSummary = { id: "t1", title: "测试线程", updated: "刚刚", pinned: false };
const LABELS = { menuLabel: "线程菜单", star: "置顶", unstar: "取消置顶", rename: "重命名", delete: "删除" };

describe("ThreadRow", () => {
  it("渲染标题与菜单按钮（aria-label 来自 labels）", () => {
    const node = ThreadRow({
      thread: THREAD, active: false, renaming: false, renameValue: "", menuOpen: false,
      labels: LABELS, onRenameChange: vi.fn(), onRenameCommit: vi.fn(), onRenameCancel: vi.fn(),
      onSelect: vi.fn(), onMenuOpenChange: vi.fn(),
    });
    const menuBtn = collectElements(
      node,
      (el) => (el.props as { ["aria-label"]?: string })["aria-label"] === "线程菜单",
    );
    expect(menuBtn).toHaveLength(1);
    const titleSpans = collectElements(
      node,
      (el) => (el.props as { children?: unknown }).children === "测试线程",
    );
    expect(titleSpans.length).toBeGreaterThan(0);
  });

  it("trailing 未提供时不渲染任何额外节点（chat 侧零变化）", () => {
    const node = ThreadRow({
      thread: THREAD, active: false, renaming: false, renameValue: "", menuOpen: false,
      labels: LABELS, onRenameChange: vi.fn(), onRenameCommit: vi.fn(), onRenameCancel: vi.fn(),
      onSelect: vi.fn(), onMenuOpenChange: vi.fn(),
    });
    const sentinelHolders = collectElements(node, (el) => (el.props as { "data-testid"?: string })["data-testid"] === "trailing-sentinel");
    expect(sentinelHolders).toHaveLength(0);
  });

  it("trailing 提供且非 active 时渲染该节点", () => {
    const sentinel = React.createElement("span", { "data-testid": "trailing-sentinel" });
    const node = ThreadRow({
      thread: THREAD, active: false, renaming: false, renameValue: "", menuOpen: false,
      labels: LABELS, trailing: sentinel, onRenameChange: vi.fn(), onRenameCommit: vi.fn(), onRenameCancel: vi.fn(),
      onSelect: vi.fn(), onMenuOpenChange: vi.fn(),
    });
    const found = collectElements(node, (el) => (el.props as { "data-testid"?: string })["data-testid"] === "trailing-sentinel");
    expect(found).toHaveLength(1);
  });

  it("trailing 提供但 active=true 时不渲染（避免与 active 圆点重叠——同一位置只留一种指示）", () => {
    const sentinel = React.createElement("span", { "data-testid": "trailing-sentinel" });
    const node = ThreadRow({
      thread: THREAD, active: true, renaming: false, renameValue: "", menuOpen: false,
      labels: LABELS, trailing: sentinel, onRenameChange: vi.fn(), onRenameCommit: vi.fn(), onRenameCancel: vi.fn(),
      onSelect: vi.fn(), onMenuOpenChange: vi.fn(),
    });
    const found = collectElements(node, (el) => (el.props as { "data-testid"?: string })["data-testid"] === "trailing-sentinel");
    expect(found).toHaveLength(0);
  });

  it("renaming=true 时渲染行内编辑输入框，不渲染菜单按钮", () => {
    const node = ThreadRow({
      thread: THREAD, active: false, renaming: true, renameValue: "编辑中", menuOpen: false,
      labels: LABELS, onRenameChange: vi.fn(), onRenameCommit: vi.fn(), onRenameCancel: vi.fn(),
      onSelect: vi.fn(), onMenuOpenChange: vi.fn(),
    });
    const inputs = collectElements(node, (el) => el.type === "input");
    expect(inputs).toHaveLength(1);
    expect((inputs[0].props as { value?: string }).value).toBe("编辑中");
    const menuBtn = collectElements(
      node,
      (el) => (el.props as { ["aria-label"]?: string })["aria-label"] === "线程菜单",
    );
    expect(menuBtn).toHaveLength(0);
  });
});

describe("ThreadMenuItems（无 hook 的纯渲染子组件）", () => {
  const base = {
    thread: THREAD, labels: LABELS,
    onStar: vi.fn(), onRename: vi.fn(), onDelete: vi.fn(),
  };
  it("默认渲染 置顶/重命名/删除 三项，不渲染添加到项目", () => {
    const node = ThreadMenuItems(base);
    const items = collectElements(node, (el) => el.type === MenuItem);
    expect(items).toHaveLength(3);
  });
  it("labels.addToProject 与 onAddProject 同时提供时渲染第四项", () => {
    const node = ThreadMenuItems({
      ...base,
      labels: { ...LABELS, addToProject: "添加到项目" },
      onAddProject: vi.fn(),
    });
    const items = collectElements(node, (el) => el.type === MenuItem);
    expect(items).toHaveLength(4);
  });
  it("labels.addToProject のみ（onAddProject 未提供）では四项目不渲染", () => {
    const node = ThreadMenuItems({
      ...base,
      labels: { ...LABELS, addToProject: "添加到项目" },
    });
    const items = collectElements(node, (el) => el.type === MenuItem);
    expect(items).toHaveLength(3);
  });
});
