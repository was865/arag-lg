"use client";

/** 共有されたスレッドの読み取り専用表示（specs/008-thread-share R6）。 */
import Link from "next/link";
import { AnswerMarkdown } from "@/components/chat/answer-markdown";
import { BrandMark, Icon } from "@/components/icons";
import type { components } from "@/lib/api/schema";
import { VISIBILITY_OPTIONS } from "@/lib/share";
import { formatDate } from "@/lib/library/view";

export type SharedThreadData = components["schemas"]["SharedThreadOut"];

export function SharedThread({ thread }: { thread: SharedThreadData }) {
  const vis = VISIBILITY_OPTIONS.find((o) => o.id === thread.visibility);
  const cite = (turn: number, n: number) => {
    const el = document.getElementById(`src-${turn}-${n}`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    el?.animate([{ background: "var(--accent-soft)" }, { background: "transparent" }], { duration: 1200 });
  };

  return (
    <div className="min-h-dvh bg-bg">
      <header className="sticky top-0 z-[5] border-b-[0.5px] border-divider bg-bg/90 backdrop-blur">
        <div className="mx-auto flex h-[52px] max-w-[860px] items-center gap-2.5 px-6 max-md:px-4">
          <Link href="/" className="flex shrink-0 items-center gap-2 text-[13px] font-semibold text-fg no-underline">
            <span className="grid h-6 w-6 place-items-center rounded-md bg-accent text-white">
              <BrandMark size={13} />
            </span>
            ARag
          </Link>
          <span className="text-muted-2">/</span>
          <h1 className="m-0 min-w-0 flex-1 truncate text-[13.5px] font-semibold text-fg">{thread.title}</h1>
          {vis && (
            <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-muted">
              <Icon name={vis.iconName} size={11} />
              {vis.label}
            </span>
          )}
        </div>
      </header>

      <main className="mx-auto flex max-w-[860px] flex-col gap-8 px-6 pb-20 pt-8 max-md:px-4">
        {thread.messages.length === 0 && (
          <p className="py-16 text-center text-[13px] text-muted">まだ回答がありません</p>
        )}
        {thread.messages.map((m, i) => (
          <article key={i} className="flex flex-col gap-3">
            <div className="ml-auto max-w-[80%] whitespace-pre-wrap rounded-[14px] bg-surface-2 px-4 py-2.5 text-[14px] leading-[1.6] text-fg [overflow-wrap:anywhere] max-md:max-w-[92%]">
              {m.query}
            </div>
            <AnswerMarkdown text={m.answer || "（回答はありません）"} onCite={(n) => cite(i, n)} citationStyle="numbered" />
            {m.sources.length > 0 && (
              <ol className="m-0 flex list-none flex-col gap-1 rounded-[10px] border-[0.5px] border-divider p-2.5">
                <li className="px-1 pb-0.5 text-[10px] font-bold uppercase tracking-[0.07em] text-muted-2">出典</li>
                {m.sources.map((s) => (
                  <li
                    key={s.n}
                    id={`src-${i}-${s.n}`}
                    className="flex items-center gap-2 rounded-md px-1 py-1 text-[12.5px] text-fg-2"
                  >
                    <span className="grid h-[18px] min-w-[18px] place-items-center rounded-[5px] bg-accent-soft px-1 font-mono text-[10.5px] font-bold text-accent">
                      {s.n}
                    </span>
                    <Icon name="doc" size={12} />
                    <span className="min-w-0 truncate">{s.title}</span>
                  </li>
                ))}
              </ol>
            )}
            <div className="text-[11px] text-muted-2">{formatDate(m.created_at)}</div>
          </article>
        ))}
      </main>
    </div>
  );
}
