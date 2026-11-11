"use client";

import { useSyncExternalStore } from "react";
import { BrandMark } from "@/components/icons";
import { TipCarousel } from "@/components/chat/tip-carousel";
import { USAGE_TIPS } from "@/lib/data";
import type { WorkspaceStats } from "@/lib/workspace-stats";
import type { AppUser } from "@/lib/types";
import { useT } from "@/i18n/context";
import type { Dictionary } from "@/i18n/dictionary";

const noopSubscribe = () => () => {};

/** 現在の時（0〜23）。prerender では時刻が決まらないので昼として描き、ブラウザで置き換える。 */
function useHour(): number {
  return useSyncExternalStore(noopSubscribe, () => new Date().getHours(), () => 12);
}

function greeting(t: Dictionary, h: number) {
  if (h < 11) return t.chat.greetingMorning;
  if (h < 18) return t.chat.greetingDay;
  return t.chat.greetingEvening;
}

interface EmptyStateProps {
  user: AppUser;
  /** 読み込み前は null（0 件と誤解されないよう指標の行を出さない）。 */
  stats: WorkspaceStats | null;
  onFillComposer: (text: string) => void;
}

export function EmptyState({ user, stats, onFillComposer }: EmptyStateProps) {
  const { t } = useT();
  const hour = useHour();
  const usageTips = USAGE_TIPS;
  const meta = stats
    ? [
        [stats.indexedDocumentCount.toLocaleString("ja-JP"), t.chat.metaIndexed],
        [stats.kbCount.toLocaleString("ja-JP"), t.chat.metaConnected],
      ]
    : [];

  return (
    <div className="grid min-h-[calc(100vh-52px-130px)] min-w-0 place-items-center px-6 py-10 max-md:min-h-0 max-md:px-[18px] max-md:py-7">
      <div className="w-full max-w-[920px] min-w-0 text-center">
        <div className="mx-auto mb-6 grid h-14 w-14 place-items-center rounded-[16px] bg-accent text-white shadow-[0_6px_20px_var(--accent-glow)] max-md:mb-[18px] max-md:h-12 max-md:w-12 max-md:rounded-sheet">
          <BrandMark size={24} className="max-md:h-[21px] max-md:w-[21px]" />
        </div>
        <h1 className="m-0 mb-2.5 font-display text-[clamp(24px,3.6vw,34px)] font-bold tracking-[0.01em] text-fg [text-wrap:balance] [word-break:keep-all] max-md:text-[clamp(20px,6.4vw,26px)]">
          {greeting(t, hour)}{t.chat.greetingConnector}<span className="text-accent">{user.firstName}</span>{t.chat.greetingSuffix}
        </h1>
        <p className="m-0 mb-9 text-headline leading-[1.55] text-muted max-md:mb-[22px] max-md:text-body">
          {t.chat.leadText}
        </p>

        <TipCarousel tips={usageTips} onFill={onFillComposer} />

        <div className="mt-9 flex min-h-[37px] justify-center gap-6 border-t-[0.5px] border-divider pt-[18px] max-md:mt-6 max-md:flex-wrap max-md:gap-x-[18px] max-md:gap-y-2.5">
          {meta.map(([a, b]) => (
            <div key={b} className="text-caption text-muted max-md:text-mini">
              <strong className="text-fg">{a}</strong>
              {b}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
