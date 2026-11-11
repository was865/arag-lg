"use client";

/**
 * 首ページ（スレッドが空のとき。specs/025 R44）。
 * 画面の中央に入力欄を置くため、挨拶（入力欄の上）と質問の候補（入力欄の下）を別の部品にする。
 * 配置は chat-app が決める。
 */
import { useEffect, useState, useSyncExternalStore } from "react";
import { Icon } from "@/components/icons";
import { USAGE_TIPS } from "@/lib/data";
import { getFileMeta } from "@/lib/file-types";
import { suggestionsFrom, type Suggestion } from "@/lib/home";
import { libraryApi } from "@/lib/library/api";
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

/** 挨拶（大きな見出し）と一言。入力欄のすぐ上に置く。 */
export function HomeHero({ user }: { user: AppUser }) {
  const { t } = useT();
  const hour = useHour();
  return (
    <div className="w-full min-w-0 px-6 pb-6 text-center max-md:px-[18px] max-md:pb-4 max-md:pt-8">
      <h1 className="m-0 animate-fade-up font-display text-hero font-bold text-fg [text-wrap:balance] [word-break:keep-all] motion-reduce:animate-none max-md:text-[clamp(22px,6.8vw,28px)]">
        {greeting(t, hour)}{t.chat.greetingConnector}{user.firstName}{t.chat.greetingSuffix}。
      </h1>
      <p className="m-0 mt-2.5 text-callout text-muted max-md:text-body">{t.chat.leadText}</p>
    </div>
  );
}

/** 質問の候補を作るための概要。読み込み前と失敗は null（候補を出さず、ヒントも出さない＝ちらつかせない）。 */
function useSuggestions(): Suggestion[] | null {
  const [items, setItems] = useState<Suggestion[] | null>(null);
  useEffect(() => {
    let alive = true;
    libraryApi.overview(null).then(
      (data) => alive && setItems(suggestionsFrom(data)),
      () => alive && setItems([]),
    );
    return () => {
      alive = false;
    };
  }, []);
  return items;
}

const CARD =
  "group flex min-w-0 animate-fade-up flex-col justify-between gap-2.5 rounded-card border-[0.5px] border-divider-strong bg-surface/70 p-3 text-left shadow-e1 transition-[transform,box-shadow,background-color] duration-(--duration-mid) ease-out hover:-translate-y-0.5 hover:bg-surface hover:shadow-e2 motion-reduce:animate-none motion-reduce:hover:translate-y-0";

/** 入力欄の下: 文書から作った質問の候補（無ければ使い方のヒント）と件数。押すと入力欄に入る（送信はしない）。 */
export function HomeSuggestions({
  stats,
  onFillComposer,
}: {
  /** 読み込み前は null（0 件と誤解されないよう件数の行を出さない）。 */
  stats: WorkspaceStats | null;
  onFillComposer: (text: string) => void;
}) {
  const { t } = useT();
  const suggestions = useSuggestions();
  const meta = stats
    ? [
        [stats.indexedDocumentCount.toLocaleString("ja-JP"), t.chat.metaIndexed],
        [stats.kbCount.toLocaleString("ja-JP"), t.chat.metaConnected],
      ]
    : [];
  return (
    <div className="mx-auto w-full max-w-[760px] min-w-0 px-8 pb-8 pt-2 max-md:px-3 max-md:pt-3">
      <div className="grid min-h-[92px] grid-cols-3 gap-2.5 max-md:grid-cols-1">
        {suggestions?.length
          ? suggestions.map((s, i) => {
              const meta = getFileMeta(s.filename);
              return (
                <button key={s.id} type="button" onClick={() => onFillComposer(s.text)} className={CARD} style={{ animationDelay: `${i * 60}ms` }}>
                  <span className="text-footnote font-medium leading-[1.55] text-fg">{s.text}</span>
                  <span className="flex min-w-0 items-center gap-1.5 text-mini text-muted">
                    <span className="shrink-0" style={{ color: meta.color }}>
                      <Icon name={meta.iconName} size={12} />
                    </span>
                    <span className="truncate">{s.filename}</span>
                  </span>
                </button>
              );
            })
          : suggestions &&
            USAGE_TIPS.slice(0, 3).map((tip, i) => (
              <button key={tip.title} type="button" onClick={() => onFillComposer(tip.fill)} className={CARD} style={{ animationDelay: `${i * 60}ms` }}>
                <span className="text-footnote font-medium leading-[1.55] text-fg">{tip.fill}</span>
                <span className="flex min-w-0 items-center gap-1.5 text-mini text-muted">
                  <Icon name={tip.icon} size={12} />
                  <span className="truncate">{tip.title}</span>
                </span>
              </button>
            ))}
      </div>
      <div className="mt-5 flex min-h-[18px] justify-center gap-5 max-md:flex-wrap max-md:gap-x-[18px] max-md:gap-y-1.5">
        {meta.map(([a, b]) => (
          <div key={b} className="text-caption text-muted max-md:text-mini">
            <strong className="nums text-fg">{a}</strong>
            {b}
          </div>
        ))}
      </div>
    </div>
  );
}
