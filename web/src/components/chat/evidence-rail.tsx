"use client";

/**
 * 根拠カードの列（specs/025 R45）。回答の横（幅が足りなければ下）に、引用した箇所ごとのカードを並べる。
 * 回答の中の印（data-cite）とカード（data-evidence）は、ホバー・フォーカスで互いに光る。
 * 連動は DOM の属性を切り替えるだけにし、回答の Markdown を描き直さない。
 */
import { Icon } from "@/components/icons";
import { Seal } from "@/components/ui/seal";
import type { Evidence } from "@/lib/chat/evidence";
import { getFileMeta } from "@/lib/file-types";
import { useT } from "@/i18n/context";
import { interpolate } from "@/i18n/interpolate";

/** 同じターンの中で、番号 n の印とカードを光らせる（消す）。 */
export function linkEvidence(from: Element, n: number, on: boolean): void {
  const turn = from.closest("[data-turn]");
  if (!turn) return;
  for (const el of turn.querySelectorAll(`[data-cite="${n}"], [data-evidence~="${n}"]`)) {
    if (on) el.setAttribute("data-on", "");
    else el.removeAttribute("data-on");
  }
}

export function EvidenceRail({ items, onOpen }: { items: Evidence[]; onOpen: (n: number) => void }) {
  const { t } = useT();
  if (items.length === 0) return null;
  return (
    <aside aria-label={t.chat.evidenceHeading} className="flex min-w-0 flex-col gap-2 @[760px]:sticky @[760px]:top-4 @[760px]:max-h-[calc(100dvh-230px)] @[760px]:self-start @[760px]:-ml-1.5 @[760px]:overflow-y-auto @[760px]:pb-1 @[760px]:pl-1.5 @[760px]:pr-1">
      <h3 className="m-0 flex items-center justify-between text-mini font-semibold uppercase tracking-[0.08em] text-muted-2">
        <span>{t.chat.evidenceHeading}</span>
        <span className="nums">{interpolate(t.chat.evidenceCount, { n: String(items.length) })}</span>
      </h3>
      <div className="flex min-w-0 flex-row flex-wrap gap-2 @[760px]:flex-col">
        {items.map((e) => {
          const meta = getFileMeta(e.title);
          const each = (on: boolean) => (ev: { currentTarget: Element }) => e.numbers.forEach((n) => linkEvidence(ev.currentTarget, n, on));
          return (
            <button
              key={`${e.sourceId}|${e.sectionId}`}
              type="button"
              data-evidence={e.numbers.join(" ")}
              onClick={() => onOpen(e.numbers[0])}
              onPointerEnter={each(true)}
              onPointerLeave={each(false)}
              onFocus={each(true)}
              onBlur={each(false)}
              title={interpolate(t.chat.openCitation, { n: String(e.numbers[0]) })}
              className="flex w-[240px] max-w-full min-w-0 flex-col gap-1.5 rounded-card border-[0.5px] border-divider-strong bg-surface p-2.5 text-left shadow-e1 outline-none transition-[transform,box-shadow,border-color] duration-(--duration-mid) ease-out hover:shadow-e2 focus-visible:ring-2 focus-visible:ring-accent/50 data-[on]:border-accent data-[on]:shadow-[0_0_0_3px_var(--accent-soft),var(--shadow-2)] @[760px]:w-full @[760px]:data-[on]:-translate-x-0.5 motion-reduce:transition-none"
            >
              <span className="flex min-w-0 items-center gap-1.5">
                {e.numbers.map((n) => (
                  <Seal key={n} n={n} />
                ))}
                <span className="shrink-0" style={{ color: meta.color }}>
                  <Icon name={meta.iconName} size={12} />
                </span>
                <span className="min-w-0 truncate text-caption font-semibold text-fg">{e.title}</span>
              </span>
              {(e.heading || e.page != null) && (
                <span className="flex min-w-0 items-center justify-between gap-2 text-mini text-muted">
                  <span className="min-w-0 truncate">{e.heading}</span>
                  {e.page != null && <span className="nums shrink-0">{interpolate(t.chat.evidencePage, { n: String(e.page) })}</span>}
                </span>
              )}
              {e.excerpt && <span className="line-clamp-3 text-caption leading-[1.6] text-fg-2 [overflow-wrap:anywhere]">{e.excerpt}</span>}
              {e.score != null && (
                <span className="flex items-center gap-2 text-mini text-muted-2">
                  <span className="h-[3px] flex-1 overflow-hidden rounded-full bg-divider">
                    <span className="block h-full rounded-full bg-accent" style={{ width: `${Math.round(Math.min(1, Math.max(0, e.score)) * 100)}%` }} />
                  </span>
                  <span className="nums font-mono">{e.score.toFixed(2)}</span>
                </span>
              )}
            </button>
          );
        })}
      </div>
    </aside>
  );
}
