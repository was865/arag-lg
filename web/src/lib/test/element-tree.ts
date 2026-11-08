// React 要素ツリー走査ヘルパ（テスト用）。RTL 非導入のため、纯函数コンポーネントを
// 直接呼んで返り値の要素ツリーを検査する。agent-sidebar.test 等と同方式。
import * as React from "react";

/** 幅優先で predicate を満たす要素を収集（函数コンポーネントは展開を試みる）。 */
export function collectElements(
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
    if (typeof current.type === "function") {
      try {
        const expanded = (current.type as (p: unknown) => React.ReactNode)(current.props);
        if (expanded) queue.push(expanded);
      } catch {
        // 展开失败（如需 hook context）则跳过
      }
    }
    const children = (current.props as { children?: React.ReactNode }).children;
    if (children) {
      if (Array.isArray(children)) queue.push(...children);
      else queue.push(children);
    }
  }
  return results;
}

/** 幅優先で文字列叶节点を収集（函数コンポーネントは展開を試みる）。 */
export function collectTexts(node: React.ReactNode): string[] {
  const results: string[] = [];
  const queue: React.ReactNode[] = [node];
  while (queue.length > 0) {
    const current = queue.shift();
    if (typeof current === "string") {
      results.push(current);
      continue;
    }
    if (!React.isValidElement(current)) {
      if (Array.isArray(current)) queue.push(...current);
      continue;
    }
    if (typeof current.type === "function") {
      try {
        const expanded = (current.type as (p: unknown) => React.ReactNode)(current.props);
        if (expanded) queue.push(expanded);
        continue;
      } catch {
        // 展开失败则降级检查 children
      }
    }
    const children = (current.props as { children?: React.ReactNode }).children;
    if (children) {
      if (Array.isArray(children)) queue.push(...children);
      else queue.push(children);
    }
  }
  return results;
}
