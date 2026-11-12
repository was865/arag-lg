"use client";

import { useState } from "react";
import { ToolSteps } from "@/components/chat/tool-steps";
import { cn, formatMs } from "@/lib/utils";
import type { Source, ToolCall, ToolView } from "@/lib/types";
import { Icon } from "@/components/icons";
import { searchStory } from "@/lib/chat/evidence";
import { CitedTitlesContext } from "@/components/chat/search-detail";
import { getFileMeta } from "@/lib/file-types";
import { interpolate } from "@/i18n/interpolate";
import { useT } from "@/i18n/context";
import { useTweaks } from "@/hooks/use-tweaks";

/** ターンのツール活動。検索の過程を 1 行と文書名で見せ、段階の明細は「詳細」で開く（実行中は開いておく）。 */
export function AgentActivity({
  steps, sources, variant, running, expandedMap, onToggleStep,
}: {
  steps: ToolCall[];
  /** この回答が引用した出典（検索の過程の「何件を引用」に使う） */
  sources?: Source[];
  variant: ToolView;
  running: boolean;
  expandedMap: Record<string, boolean>;
  onToggleStep: (id: string) => void;
}) {
  // 段階の明細は既定で畳む（実行中は見出しに今の段階名が流れる）。利用者が開閉した値を優先する。
  const [open, setOpen] = useState<boolean | null>(null);
  const isOpen = open ?? false;
  const { t } = useT();
  const { tweaks } = useTweaks();

  // 推論過程（reasoning）の表示はユーザー設定（既定オフ）。集計・現在段階・描画を
  // 揃えるため、ここで一度だけ除外したリストを以降すべてに使う。
  const visibleSteps = tweaks.showReasoning ? steps : steps.filter((s) => s.name !== "reasoning");

  if (visibleSteps.length === 0) return null;

  // 子サブステップの ms は親 retrieve の duration に内包されるため、集計はトップレベルのみ。
  const topLevel = visibleSteps.filter((s) => !s.parentId);
  const totalMs = topLevel.reduce((a, s) => a + (s.durationMs || 0), 0);
  // 現在段階インジケータ: running な leaf（子）を優先し、無ければトップレベルの running。
  const runningSteps = visibleSteps.filter((s) => s.status === "running");
  const current = runningSteps.find((s) => s.parentId) ?? runningSteps[0];
  // 推論を隠していても、考えている最中なら「実行中」より具体的に言う（検索の合間に長く考えることがある）
  const thinking = steps.some((s) => s.name === "reasoning" && s.status === "running");

  const story = searchStory(visibleSteps, sources ?? []);
  const SHOWN = 4;
  const check = (
    <span className="grid h-3.5 w-3.5 shrink-0 place-items-center rounded-full bg-accent-soft text-accent">
      <svg viewBox="0 0 16 16" width="9" height="9" aria-hidden>
        <path d="M4 8.3l2.6 2.5L12 5.4" stroke="currentColor" strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );

  // 検索の過程（specs/025 R45）: 「何件探し、何件引用したか」と文書名を見せ、段階の明細は「詳細」に畳む
  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={() => setOpen(!isOpen)}
        aria-expanded={isOpen}
        className="flex w-full flex-wrap items-center gap-x-2 gap-y-1 rounded-control border-0 bg-transparent p-0 text-left text-footnote text-muted outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
      >
        {running ? (
          <span className="inline-flex items-center gap-2">
            <span className="h-3 w-3 animate-spin-fast rounded-full border-[1.5px] border-divider-strong border-t-accent" />
            <span className="text-shimmer font-medium">{current?.summary ?? (thinking ? t.chat.storyThinking : t.chat.agentRunning)}</span>
          </span>
        ) : story.searched > 0 ? (
          <>
            <span className="inline-flex items-center gap-1.5">{check}{interpolate(t.chat.storySearched, { n: String(story.searched) })}</span>
            <span className="text-muted-2">›</span>
            {story.cited > 0 ? (
              <span className="inline-flex items-center gap-1.5">{check}{interpolate(t.chat.storyCited, { n: String(story.cited) })}</span>
            ) : (
              // 探したのに 1 つも引用していない回答は、根拠をたどれない。済みの印でなく注意として出す
              <span className="inline-flex items-center gap-1.5 font-medium text-danger">
                <Icon name="alert" size={12} />
                {t.chat.storyCitedNone}
              </span>
            )}
          </>
        ) : (
          <span className="inline-flex items-center gap-1.5">{check}{t.chat.storyNoSearch}</span>
        )}
        <span className="ml-auto inline-flex items-center gap-1.5 font-mono text-caption text-muted-2">
          <span className="nums">{formatMs(totalMs)}</span>
          <span className="font-sans">· {t.chat.storyDetail}</span>
          <span className={cn("transition-transform duration-(--duration-mid)", isOpen && "rotate-180")}>
            <svg viewBox="0 0 16 16" width="11" height="11" aria-hidden>
              <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        </span>
      </button>
      {story.files.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {story.files.slice(0, SHOWN).map((f, i) => {
            const meta = getFileMeta(f.title);
            return (
              <span
                key={f.title}
                style={{ animationDelay: `${i * 50}ms` }}
                className={cn(
                  "inline-flex max-w-[240px] animate-fade-up items-center gap-1.5 rounded-control border-[0.5px] border-divider-strong bg-surface py-1 pl-1.5 pr-2 text-caption motion-reduce:animate-none",
                  f.cited ? "text-fg shadow-e1" : "text-muted opacity-60",
                )}
              >
                <span className="shrink-0" style={{ color: meta.color }}>
                  <Icon name={meta.iconName} size={12} />
                </span>
                <span className="truncate">{f.title}</span>
              </span>
            );
          })}
          {story.files.length > SHOWN && (
            // 折り返して 1 つだけ次の行に出ても浮かないよう、文書の札と同じ高さの札にする
            <span className="inline-flex items-center rounded-control border-[0.5px] border-dashed border-divider-strong px-2 py-1 text-caption text-muted">

              {interpolate(t.chat.storyMore, { n: String(story.files.length - SHOWN) })}
            </span>
          )}
        </div>
      )}
      {isOpen && (
        <div className="animate-fade-up overflow-hidden rounded-card border-[0.5px] border-divider-strong bg-surface-2 motion-reduce:animate-none">
          <CitedTitlesContext.Provider value={new Set((sources ?? []).map((x) => x.title))}>
            <ToolSteps steps={visibleSteps} variant={variant} expandedMap={expandedMap} onToggleStep={onToggleStep} />
          </CitedTitlesContext.Provider>
        </div>
      )}
    </div>
  );
}
