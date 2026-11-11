"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { cn } from "@/lib/utils";
import type { CitationStyle } from "@/lib/types";
import { useT } from "@/i18n/context";
import { interpolate } from "@/i18n/interpolate";
import { remarkCitations } from "@/components/chat/remark-citations";
import { sealClass } from "@/components/ui/seal";

export interface AnswerMarkdownProps {
  text: string;
  onCite: (n: number) => void;
  citationStyle: CitationStyle;
  className?: string;
}

function citeBtnClass(style: CitationStyle) {
  const base =
    "inline-flex cursor-pointer items-center justify-center border-0 font-mono leading-none transition-[background,transform] duration-100 hover:-translate-y-px";
  if (style === "chip")
    return cn(base, "mx-0.5 h-[18px] rounded-control border border-accent-soft bg-surface px-[5px] text-mini font-semibold text-accent hover:bg-accent-soft");
  if (style === "pill")
    return cn(base, "mx-0.5 h-[18px] rounded-full bg-accent px-[7px] text-mini font-semibold text-white");
  // numbered: 朱の印（specs/025 R43）。ホバーで少し浮き、周りに淡い輪が出る
  return cn(sealClass({ size: "sm" }), "mx-0.5 cursor-pointer border-0 align-[2px] transition-[transform,box-shadow] duration-(--duration-fast) hover:-translate-y-px hover:scale-110 hover:shadow-[0_0_0_4px_var(--accent-soft)] motion-reduce:hover:transform-none");
}

/** 引用番号ボタン。クリックで該当出典を開く（onCite）。 */
function CitationButton({ n, style, onCite }: { n: number; style: CitationStyle; onCite: (n: number) => void }) {
  const { t } = useT();
  return (
    <button
      className={citeBtnClass(style)}
      title={interpolate(t.chat.openCitation, { n: String(n) })}
      onClick={() => onCite(n)}
    >
      {style === "chip" ? `[${n}]` : n}
    </button>
  );
}

/**
 * 回答本文にインライン表示された markdown 画像を描画する。
 * セキュリティ: 自社アセット (/api/documents/...) のみ描画する。外部 URL や
 * 未解決の相対パスは、悪意ある文書に誘導されたエージェントによる外部取得・
 * 情報漏洩の経路になりうるため画像化せずテキストとして扱う。
 */
function AnswerImage({ src, alt }: { src: string; alt: string }) {
  const [failed, setFailed] = useState(false);
  const { t } = useT();
  if (!src.startsWith("/api/documents/")) {
    return <span>{alt || src}</span>;
  }
  if (failed) {
    return (
      <span className="text-footnote text-muted">
        {interpolate(t.chat.imageLoadError, { alt: alt ? alt : "" })}
      </span>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element -- 認証付き動的アセットのため next/image は使わない
    <img
      src={src}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
      className="my-2 block max-w-full rounded-[8px] border-[0.5px] border-divider"
    />
  );
}

// 見出し/段落/リスト/コード/表/区切り/画像をデザイントークンに合わせて装飾する。
// チャット本文の既定 14.5px に合わせ、見出しは MarkdownView より一段小さく抑える。
const ANSWER_PROSE = [
  "text-callout leading-[1.7] text-fg-2 [overflow-wrap:anywhere]",
  "[&>*:first-child]:mt-0 [&>*:last-child]:mb-0",
  "[&_h1]:mt-4 [&_h1]:mb-2 [&_h1]:text-title [&_h1]:font-bold [&_h1]:tracking-[-0.005em] [&_h1]:text-fg",
  "[&_h2]:mt-4 [&_h2]:mb-2 [&_h2]:text-headline [&_h2]:font-bold [&_h2]:tracking-[-0.005em] [&_h2]:text-fg",
  "[&_h3]:mt-3.5 [&_h3]:mb-1.5 [&_h3]:text-callout [&_h3]:font-semibold [&_h3]:text-fg",
  "[&_h4]:mt-3 [&_h4]:mb-1 [&_h4]:text-body [&_h4]:font-semibold [&_h4]:text-fg",
  "[&_p]:my-2",
  "[&_strong]:font-semibold [&_strong]:text-fg",
  "[&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5",
  "[&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5",
  "[&_li]:my-0.5 [&_li]:marker:text-muted",
  "[&_blockquote]:my-2 [&_blockquote]:border-l-2 [&_blockquote]:border-divider-strong [&_blockquote]:pl-3 [&_blockquote]:text-muted",
  "[&_code]:rounded [&_code]:bg-surface-2 [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-footnote",
  "[&_pre]:my-3 [&_pre]:overflow-x-auto [&_pre]:rounded-[8px] [&_pre]:border-[0.5px] [&_pre]:border-divider [&_pre]:bg-surface-2 [&_pre]:p-3",
  "[&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-footnote",
  "[&_table]:my-3 [&_table]:block [&_table]:w-fit [&_table]:max-w-full [&_table]:overflow-x-auto [&_table]:border-collapse [&_table]:text-footnote",
  "[&_th]:border-[0.5px] [&_th]:border-divider [&_th]:bg-surface-2 [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_th]:font-semibold [&_th]:text-fg",
  "[&_td]:border-[0.5px] [&_td]:border-divider [&_td]:px-2 [&_td]:py-1",
  "[&_hr]:my-4 [&_hr]:border-divider",
  "[&_a]:text-accent [&_a]:underline",
].join(" ");

/**
 * チャット回答を完全な Markdown(GFM: 見出し・表・区切り・コード・タスクリスト、
 * および数式)として整形描画する。markdown-lite だった旧 CitedText を置き換える。
 * 引用番号 [N] はクリック可能なボタン、画像は自社アセットのみ描画する。
 * セキュリティ上、生 HTML は描画しない(rehype-raw 不使用)。
 */
export function AnswerMarkdown({ text, onCite, citationStyle, className }: AnswerMarkdownProps) {
  return (
    <div className={cn(ANSWER_PROSE, className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath, remarkCitations]}
        rehypePlugins={[rehypeKatex]}
        components={{
          a: ({ href, children }) => {
            if (typeof href === "string" && href.startsWith("#cite-")) {
              const n = Number(href.slice("#cite-".length));
              if (Number.isFinite(n)) return <CitationButton n={n} style={citationStyle} onCite={onCite} />;
            }
            return (
              <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
            );
          },
          img: ({ src, alt }) => <AnswerImage src={typeof src === "string" ? src : ""} alt={alt ?? ""} />,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
