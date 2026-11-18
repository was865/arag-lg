"use client";

/**
 * 根拠カードの列（specs/025 R45）。回答の横（幅が足りなければ下）に、引用した箇所ごとのカードを並べる。
 * 回答の中の印（data-cite）とカード（data-evidence）は、ホバー・フォーカスで互いに光る。
 * 連動は DOM の属性を切り替えるだけにし、回答の Markdown を描き直さない。
 */
import { Icon } from "@/components/icons";
import { cardClass } from "@/components/ui/card";
import { Seal } from "@/components/ui/seal";
import { overflowData, useOverflow } from "@/components/ui/use-overflow";
import type { Evidence } from "@/lib/chat/evidence";
import { getFileMeta } from "@/lib/file-types";
import { useT } from "@/i18n/context";
import { interpolate } from "@/i18n/interpolate";
import { cn } from "@/lib/utils";

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
  const { ref: listRef, overflow } = useOverflow<HTMLDivElement>();
  if (items.length === 0) return null;
  return (
    // 横並びのときは、この外枠の高さを回答本文に合わせる（contain:size で中身の高さを行の高さに数えない）。
    // カードが多ければカードの列だけが内側で縦にスクロールし（見出しは残す）、回答の終わりと一回分の下端（操作の行）がそろう。
    // 続きのある端は薄くして、カードが途中で切れて見えないようにする（scroll-fade-*）。
    <div className="min-w-0 @[760px]:relative @[760px]:min-h-[200px] @[760px]:[contain:size]">
    <aside aria-label={t.chat.evidenceHeading} className="flex min-w-0 flex-col gap-2 @[760px]:sticky @[760px]:top-0 @[760px]:max-h-[min(100%,calc(100dvh-230px))]">
      <h3 className="eyebrow m-0 flex shrink-0 items-center justify-between">
        <span>{t.chat.evidenceHeading}</span>
        <span className="nums">{interpolate(t.chat.evidenceCount, { n: String(items.length) })}</span>
      </h3>
      {/* 狭いときは横に滑らせる一列（縦に積むと画面を占めるため）。影と光りが切れないよう周りに余白を取る */}
      <div
        ref={listRef}
        {...overflowData(overflow)}
        className="scroll-fade-x -mx-1 -my-1 flex min-w-0 snap-x snap-proximity flex-row gap-2 overflow-x-auto px-1 py-1 [scrollbar-width:none] @[760px]:scroll-fade-y @[760px]:-mx-1.5 @[760px]:min-h-0 @[760px]:snap-none @[760px]:flex-col @[760px]:overflow-x-visible @[760px]:overflow-y-auto @[760px]:px-1.5 @[760px]:pb-2 [&::-webkit-scrollbar]:hidden"
      >
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
              className={cn(
                cardClass({ tone: "linked" }),
                "flex w-[220px] max-w-[78%] min-w-0 shrink-0 snap-start flex-col gap-1.5 p-2.5 text-left @[760px]:w-full @[760px]:max-w-full @[760px]:shrink-0 @[760px]:data-[on]:-translate-x-0.5",
              )}
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
              {e.excerpt && <span className="line-clamp-2 text-caption @[760px]:line-clamp-3 leading-[1.6] text-fg-2 [overflow-wrap:anywhere]">{e.excerpt}</span>}
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
    </div>
  );
}
