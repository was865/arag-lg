// AppShell 节点层测试：遍历 React 元素树，验证插槽渲染与受控布局属性。
// 不依赖 @testing-library/react，与 agent-sidebar.test.tsx 保持一致风格。
import { describe, it, expect, vi } from "vitest";
import * as React from "react";
import { AppShell } from "@/components/shell/app-shell";

// 广度优先遍历，收集满足 predicate 的元素（不展开含 hook 的子组件）。
function collectElements(
  node: React.ReactNode,
  predicate: (el: React.ReactElement) => boolean,
): React.ReactElement[] {
  const results: React.ReactElement[] = [];
  const queue: React.ReactNode[] = [node];
  while (queue.length > 0) {
    const current = queue.shift();
    if (!React.isValidElement(current)) {
      if (Array.isArray(current)) queue.push(...current);
      continue;
    }
    if (predicate(current)) results.push(current);
    const children = (current.props as { children?: React.ReactNode }).children;
    if (children) {
      if (Array.isArray(children)) queue.push(...children);
      else queue.push(children);
    }
  }
  return results;
}

function collectTexts(node: React.ReactNode): string[] {
  const out: string[] = [];
  const queue: React.ReactNode[] = [node];
  while (queue.length > 0) {
    const current = queue.shift();
    if (typeof current === "string") { out.push(current); continue; }
    if (!React.isValidElement(current)) {
      if (Array.isArray(current)) queue.push(...current);
      continue;
    }
    const children = (current.props as { children?: React.ReactNode }).children;
    if (children) {
      if (Array.isArray(children)) queue.push(...children);
      else queue.push(children);
    }
  }
  return out;
}

const base = {
  sidebar: <div data-testid="sb">SIDEBAR</div>,
  children: <main data-testid="main">MAIN</main>,
  sidebarCollapsed: false,
  rightPanelShown: false,
  panelWidth: 360,
  compact: false,
  backdropVisible: false,
  onBackdropClick: () => {},
};

describe("AppShell（节点层测试）", () => {
  it("渲染 sidebar 与 children 插槽", () => {
    const node = AppShell({ ...base });
    const texts = collectTexts(node);
    expect(texts).toContain("SIDEBAR");
    expect(texts).toContain("MAIN");
  });

  it("提供 rightPanel 时渲染、未提供时不渲染", () => {
    const withRp = AppShell({ ...base, rightPanel: <aside>RIGHT</aside>, rightPanelShown: true });
    expect(collectTexts(withRp)).toContain("RIGHT");
    const withoutRp = AppShell({ ...base });
    expect(collectTexts(withoutRp)).not.toContain("RIGHT");
  });

  it("data-sb 反映 sidebarCollapsed", () => {
    const open = AppShell({ ...base, sidebarCollapsed: false });
    const collapsed = AppShell({ ...base, sidebarCollapsed: true });
    const rootOf = (n: React.ReactNode) =>
      collectElements(n, (el) => Boolean((el.props as Record<string, unknown>)["data-sb"]))[0]
      ?? collectElements(n, (el) => "data-sb" in (el.props as object))[0];
    expect((rootOf(open)!.props as Record<string, unknown>)["data-sb"]).toBe("open");
    expect((rootOf(collapsed)!.props as Record<string, unknown>)["data-sb"]).toBe("collapsed");
  });

  it("data-rp 反映 rightPanelShown，并设置 --rp-width", () => {
    const node = AppShell({ ...base, rightPanelShown: true, panelWidth: 420 });
    const root = collectElements(node, (el) => "data-rp" in (el.props as object))[0];
    expect((root.props as Record<string, unknown>)["data-rp"]).toBe("open");
    const style = (root.props as { style?: Record<string, string> }).style ?? {};
    expect(style["--rp-width"]).toBe("420px");
  });

  it("backdrop 反映 backdropVisible 且点击触发 onBackdropClick", () => {
    const onBackdropClick = vi.fn();
    const node = AppShell({ ...base, backdropVisible: true, onBackdropClick });
    const backdrop = collectElements(node, (el) => "data-visible" in (el.props as object))[0];
    expect((backdrop.props as Record<string, unknown>)["data-visible"]).toBe("true");
    (backdrop.props as { onClick?: () => void }).onClick?.();
    expect(onBackdropClick).toHaveBeenCalledOnce();
  });
});
