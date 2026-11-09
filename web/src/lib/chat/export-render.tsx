/** 書き出し用の Markdown → HTML。画面と同じ react-markdown を使い、生の HTML は通さない（エスケープされる）。
 *  react-dom/server を含むので、書き出すときだけ動的に読み込む。 */
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

export function renderMarkdown(md: string): string {
  return renderToStaticMarkup(
    <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
      {md}
    </ReactMarkdown>,
  );
}
