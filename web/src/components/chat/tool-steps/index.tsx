"use client";

/** エージェントの段階の一覧（「詳細」の中身）。段階をまとめ、子の段階とシステムの処理を畳んで出す。
 * 部品は同じフォルダに分けてある: 共通 shared・入力 step-input・出力 step-output・見せ方 step-views・システムの処理 system-fields・表 table-result。 */
import { useState } from "react";
import { SearchDetail, searchHits } from "@/components/chat/search-detail";
import { cn } from "@/lib/utils";
import type { ToolCall, ToolView } from "@/lib/types";
import { useT } from "@/i18n/context";
import { interpolate } from "@/i18n/interpolate";
import type { Dictionary } from "@/i18n/dictionary";
import { StatusIcon, TOOL_ICONS, hasInputData, inputSectionLabel, isExpandable, outputSectionLabel, sectionLabelCls, stepDurationLabel } from "./shared";
import { ToolInputBlock } from "./step-input";
import { ToolOutputBlock } from "./step-output";
import { SystemCallView } from "./system-call";
import { ToolStepCard, ToolStepLog, ToolStepTimeline } from "./step-views";

export interface Props {
  steps: ToolCall[];
  variant: ToolView;
  expandedMap: Record<string, boolean>;
  onToggleStep: (id: string) => void;
  /** 「システムの処理」を最初から開いておく（管理者が報告を読むとき。specs/028 R14） */
  systemOpen?: boolean;
}

/** フラットな steps を「ルート(parentId なし)」と「子(parentId 別)」に分ける。 */
export function groupSteps(steps: ToolCall[]): { roots: ToolCall[]; childrenOf: Map<string, ToolCall[]> } {
  const roots: ToolCall[] = [];
  const childrenOf = new Map<string, ToolCall[]>();
  for (const s of steps) {
    if (s.parentId) {
      const arr = childrenOf.get(s.parentId) ?? [];
      arr.push(s);
      childrenOf.set(s.parentId, arr);
    } else {
      roots.push(s);
    }
  }
  return { roots, childrenOf };
}

/** 子サブステップの行。詳細があれば展開可能。card / timeline 共通。 */
export function SubStepRow({ step, expanded, onToggle, t }: { step: ToolCall; expanded: boolean; onToggle: () => void; t: Dictionary }) {
  const expandable = isExpandable(step);
  const hits = searchHits(step);
  const showInput = hasInputData(step.input);
  const showOutput = step.output != null;
  return (
    <div data-step={step.id}>
      <button
        type="button"
        onClick={expandable ? onToggle : undefined}
        aria-expanded={expandable ? expanded : undefined}
        className={cn(
          "flex w-full items-center gap-2.5 border-0 bg-transparent py-[3px] text-left text-caption text-fg-2",
          expandable ? "cursor-pointer hover:text-fg" : "cursor-default",
        )}
      >
        <StatusIcon status={step.status} t={t} name={step.name} />
        <span className="grid place-items-center text-muted-2">
          <svg viewBox="0 0 16 16" width="12" height="12">{TOOL_ICONS[step.name]}</svg>
        </span>
        <span className="truncate text-caption font-semibold text-fg-2">{step.label || step.name}</span>
        <span className="font-mono text-mini text-muted-2 max-md:hidden">{step.label ? step.name : ""}</span>
        <span className="min-w-0 flex-1 truncate text-muted">{step.summary}</span>
        <span className="font-mono text-mini tabular-nums text-muted-2">{stepDurationLabel(step)}</span>
        {expandable ? (
          <span className={cn("text-muted-2 transition-transform", expanded && "rotate-180")}>
            <svg viewBox="0 0 16 16" width="10" height="10">
              <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        ) : (
          <span aria-hidden className="block h-[10px] w-[10px]" />
        )}
      </button>
      {expandable && expanded && hits && (
        <div className="pb-2 pl-[26px] pt-1">
          <SearchDetail step={step} hits={hits} />
        </div>
      )}
      {expandable && expanded && !hits && step.name === "system_query" && (
        <div className="pb-2 pl-[26px] pt-1">
          <SystemCallView step={step} t={t} />
        </div>
      )}
      {expandable && expanded && !hits && step.name !== "system_query" && (
        <div className="flex flex-col gap-2 pb-2 pl-[26px] pt-1">
          {showInput && (
            <div>
              <div className={sectionLabelCls}>{inputSectionLabel(step, t)}</div>
              <ToolInputBlock step={step} t={t} />
            </div>
          )}
          {showOutput && (
            <div>
              <div className={sectionLabelCls}>{outputSectionLabel(step, t)}</div>
              <ToolOutputBlock step={step} t={t} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** 自動の検索が何のために行われたか（質問文での検索・整理したクエリでの検索）。 */
export function PurposeNote({ step }: { step: ToolCall }) {
  const purpose = step.input.purpose;
  if (typeof purpose !== "string" || !purpose) return null;
  return <div className="pb-1.5 text-caption leading-[1.5] text-muted">{purpose}</div>;
}

export function SubSteps({ steps, expandedMap, onToggleStep, t }: {
  steps: ToolCall[] | undefined;
  expandedMap: Record<string, boolean>;
  onToggleStep: (id: string) => void;
  t: Dictionary;
}) {
  if (!steps || steps.length === 0) return null;
  // 親（資料を検索）の中身が検索 1 回だけなら、同じことを 2 段で言わず、明細をそのまま出す
  const only = steps.length === 1 ? steps[0] : null;
  const onlyHits = only ? searchHits(only) : null;
  if (only && onlyHits) return <SearchDetail step={only} hits={onlyHits} />;
  return (
    <div className="flex flex-col gap-px border-l-[1.5px] border-divider pl-3 ml-[7px]">
      {steps.map((s) => (
        <SubStepRow key={s.id} step={s} expanded={!!expandedMap[s.id]} onToggle={() => onToggleStep(s.id)} t={t} />
      ))}
    </div>
  );
}

/**
 * システムの処理（引用の整形・ツールの必須化・回数の上限・前のターンの省略・会話の要約）を 1 組に畳む。
 * 記録には全部残すが、エージェントが自分で行った段階（検索・読む・計算・見直し）の流れを邪魔しないよう、
 * 末尾に件数だけを出し、開くと 1 件 1 行、さらに開くと中身が見える（3 段で深くなる）。
 */
export function SystemGroup({ steps, expandedMap, onToggleStep, t, defaultOpen = false }: {
  steps: ToolCall[];
  expandedMap: Record<string, boolean>;
  onToggleStep: (id: string) => void;
  t: Dictionary;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (steps.length === 0) return null;
  return (
    <div className="border-t-[0.5px] border-divider">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-2.5 border-0 bg-transparent px-3.5 py-2 text-left text-caption text-muted outline-none hover:text-fg-2 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/50 max-md:px-3"
      >
        <span className="grid place-items-center text-muted-2">
          <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden>{TOOL_ICONS.system}</svg>
        </span>
        <span className="shrink-0 font-medium">{t.chat.systemGroup}</span>
        <span className="nums shrink-0 text-muted-2">{interpolate(t.chat.systemCount, { n: String(steps.length) })}</span>
        {/* 畳んでいる間は何をしたかを名前だけ並べる */}
        {!open && <span className="min-w-0 flex-1 truncate text-muted-2 max-md:hidden">{steps.map((s) => s.label).join("・")}</span>}
        <span className={cn("ml-auto text-muted-2 transition-transform", open && "rotate-180")}>
          <svg viewBox="0 0 16 16" width="10" height="10" aria-hidden>
            <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </button>
      {open && (
        <div className="animate-fade-up px-3.5 pb-2 motion-reduce:animate-none max-md:px-3">
          <div className="ml-[5px] flex flex-col gap-px border-l-[1.5px] border-divider pl-3">
            {steps.map((s) => (
              <SubStepRow key={s.id} step={s} expanded={!!expandedMap[s.id]} onToggle={() => onToggleStep(s.id)} t={t} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function ToolSteps({ steps, variant, expandedMap, onToggleStep, systemOpen }: Props) {
  const { t } = useT();
  // 生の記録（log）は全部を時刻順に出す
  if (variant === "log") return <ToolStepLog steps={steps} dict={t} />;
  // 系統が導く流れのターンは、RunFlow が経路とステップを 1 つにして出す（specs/029 T37）。ここは古い回答と生の記録

  const system = steps.filter((s) => s.name === "system" && !s.parentId);
  const { roots, childrenOf } = groupSteps(steps.filter((s) => !system.includes(s)));

  if (variant === "timeline") {
    return (
      <div className="px-3.5 pb-3 pt-2 max-md:px-3">
        {roots.map((s, i) => (
          <div key={s.id}>
            <ToolStepTimeline step={s} expanded={!!expandedMap[s.id]} onToggle={() => onToggleStep(s.id)} isLast={i === roots.length - 1} t={t} hasChildren={childrenOf.has(s.id)} />
            {childrenOf.has(s.id) && expandedMap[s.id] && (
              <div className="mb-2 ml-[22px] animate-fade-up pl-1 motion-reduce:animate-none">
                <PurposeNote step={s} />
                <SubSteps steps={childrenOf.get(s.id)} expandedMap={expandedMap} onToggleStep={onToggleStep} t={t} />
              </div>
            )}
          </div>
        ))}
        <SystemGroup steps={system} expandedMap={expandedMap} onToggleStep={onToggleStep} t={t} defaultOpen={systemOpen} />
      </div>
    );
  }
  return (
    <div className="flex flex-col">
      {roots.map((s) => (
        <div key={s.id}>
          <ToolStepCard step={s} expanded={!!expandedMap[s.id]} onToggle={() => onToggleStep(s.id)} t={t} hasChildren={childrenOf.has(s.id)} />
          {childrenOf.has(s.id) && expandedMap[s.id] && (
            <div className="animate-fade-up border-b-[0.5px] border-divider bg-surface px-3.5 py-2 pl-10 motion-reduce:animate-none max-md:pl-6">
              <PurposeNote step={s} />
              <SubSteps steps={childrenOf.get(s.id)} expandedMap={expandedMap} onToggleStep={onToggleStep} t={t} />
            </div>
          )}
        </div>
      ))}
      <SystemGroup steps={system} expandedMap={expandedMap} onToggleStep={onToggleStep} t={t} defaultOpen={systemOpen} />
    </div>
  );
}
