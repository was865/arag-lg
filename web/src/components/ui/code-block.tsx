"use client";

/**
 * 等幅の文の面（SQL・RPC・JSON・モデルに渡した文）。言語の札と写すボタンを付け、長い文は高さを抑えて中で滑らせる。
 * 色は控えめに: キーワードは fg の太字、文字列は muted、数は fg-2。accent（朱）は使わない（AGENTS.md の色の使い分け）。
 */
import { useState } from "react";
import { cn } from "@/lib/utils";
import { codeTokens } from "@/lib/chat/system-call";
import { Icon } from "@/components/icons";

const TONE = {
  kw: "font-semibold text-fg",
  name: "text-fg",
  str: "text-muted",
  num: "text-fg-2",
  plain: "text-fg-2",
} as const;

export function CodeBlock({
  code,
  lang,
  label,
  meta,
  copyLabel = "コピー",
  copiedLabel = "コピーしました",
  maxHeight = 240,
  className,
  children,
}: {
  code: string;
  /** sql・odoo は語を色分けする。ほかはそのまま */
  lang?: string;
  /** 左上の札（「SQL」など）。無ければ出さない */
  label?: React.ReactNode;
  /** 右上の補足（時間・件数） */
  meta?: React.ReactNode;
  copyLabel?: string;
  copiedLabel?: string;
  maxHeight?: number;
  className?: string;
  /** 文を自分で組んで見せるとき（写すのは code）。無ければ code を色分けして出す */
  children?: React.ReactNode;
}) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      // 写せない環境（http・権限なし）では何もしない。文は選んで写せる
    }
  };
  const tokens = lang === "sql" || lang === "odoo" ? codeTokens(lang, code) : null;
  return (
    <div className={cn("group/code relative rounded-control border-[0.5px] border-divider bg-code-bg", className)}>
      <div className="flex items-center gap-2 px-3 pt-2 text-mini text-muted">
        {label && <span className="font-mono font-semibold uppercase tracking-[0.04em] text-muted">{label}</span>}
        <span className="min-w-0 flex-1 truncate font-mono tabular-nums">{meta}</span>
        <button
          type="button"
          onClick={() => void copy()}
          aria-label={copied ? copiedLabel : copyLabel}
          title={copied ? copiedLabel : copyLabel}
          className="inline-flex h-5 items-center gap-1 rounded-[5px] px-1 text-muted outline-none hover:bg-divider hover:text-fg focus-visible:ring-2 focus-visible:ring-accent/50"
        >
          <Icon name={copied ? "check" : "copy"} size={12} />
          <span className="max-md:hidden">{copied ? copiedLabel : copyLabel}</span>
        </button>
      </div>
      <pre
        className="m-0 overflow-auto whitespace-pre-wrap break-all px-3 pb-2.5 pt-1 font-mono text-caption leading-[1.6]"
        style={{ maxHeight }}
      >
        {children ??
          (tokens
          ? tokens.map((tok, i) => (
              <span key={i} className={TONE[tok.k]}>
                {tok.t}
              </span>
            ))
          : <span className="text-fg-2">{code}</span>)}
      </pre>
    </div>
  );
}
