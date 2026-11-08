/**
 * 回答本文中の素の引用トークン [N]（連続 [N][M] も可）を、クリック可能な
 * 引用ボタンへ変換するための remark プラグイン。AST の text ノードのみを
 * 走査するため、コードブロックや inlineCode・既存リンク内の [N] は対象外
 * （生テキストのまま残る）。
 *
 * 変換先は url="#cite-N" の link ノード。react-markdown 側で <a> を override し、
 * この href を検出して引用ボタンへ差し替える（answer-markdown.tsx）。
 */

// @types/mdast / unist-util-visit は未宣言の transitive 依存のため直接 import せず、
// 必要最小限の局所型で AST を扱う。
import { citationMarkerHasMatch, citationMarkerNumber, citationMarkerPattern } from "@/lib/citation-markers";

interface MdNode {
  type: string;
  value?: string;
  url?: string;
  children?: MdNode[];
}

function splitCitations(value: string): MdNode[] {
  const out: MdNode[] = [];
  const re = citationMarkerPattern();
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(value)) !== null) {
    if (m.index > last) out.push({ type: "text", value: value.slice(last, m.index) });
    const n = citationMarkerNumber(m);
    out.push({ type: "link", url: `#cite-${n}`, children: [{ type: "text", value: n }] });
    last = m.index + m[0].length;
  }
  if (last < value.length) out.push({ type: "text", value: value.slice(last) });
  return out;
}

function transform(node: MdNode): void {
  if (!node.children) return;
  const next: MdNode[] = [];
  for (const child of node.children) {
    // link 内は二重リンク化を避けるため走査しない。code/inlineCode は children を
    // 持たない（value のみ）ため、ここで text として拾われることはない。
    if (child.type === "text" && child.value && citationMarkerHasMatch(child.value)) {
      next.push(...splitCitations(child.value));
    } else {
      if (child.type !== "link") transform(child);
      next.push(child);
    }
  }
  node.children = next;
}

/** remark プラグイン本体。mdast を破壊的に書き換える。 */
export function remarkCitations() {
  return (tree: MdNode): void => transform(tree);
}

// テスト用に内部関数を公開する。
export const __test = { splitCitations, transform };
