/**
 * UI の文言（日本語のみ）。画面に出す文はすべてここの辞書（locales/ja/）に置き、部品では `t.画面.キー` で使う。
 * - React の部品でも lib の関数でもサーバーでも、`import { t } from "@/i18n"` で読める（言語は 1 つなので切り替えない）。
 * - 差し込みは `interpolate(t.library.selected, { n })`（辞書の文は "{n} 件を選択"）。
 * - 既存の `useT()` も同じ辞書を返す。
 */
import { ja } from "./locales/ja";

export const t = ja;
export type { Dictionary } from "./dictionary";
