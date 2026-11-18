/** 1 つの段階の見せ方（カード・時系列・ログ）。 */
import { cn, formatMs } from "@/lib/utils";
import type { ToolCall } from "@/lib/types";
import { interpolate } from "@/i18n/interpolate";
import type { Dictionary } from "@/i18n/dictionary";
import { AutoBadge, LOG_DETAIL_MAX, StatusIcon, TOOL_ICONS, hasInputData, inputSectionLabel, isBySystem, isExpandable, outputSectionLabel, sectionLabelCls, stepDurationLabel } from "./shared";
import { ToolInputBlock } from "./step-input";
import { ToolOutputBlock } from "./step-output";

export function ToolStepCard({ step, expanded, onToggle, t, hasChildren = false }: { step: ToolCall; expanded: boolean; onToggle: () => void; t: Dictionary; hasChildren?: boolean }) {
  // 子（検索の明細など）を持つ段階は、開閉で子を出す。自分の入力・出力は子と同じ内容なので出さない
  const expandable = hasChildren || isExpandable(step);
  const showInput = !hasChildren && hasInputData(step.input);
  const showOutput = !hasChildren && step.output != null;
  return (
    <div className="border-b-[0.5px] border-divider last:border-b-0">
      <button
        type="button"
        onClick={expandable ? onToggle : undefined}
        aria-expanded={expandable ? expanded : undefined}
        className={cn(
          "grid w-full grid-cols-[16px_16px_auto_auto_1fr_auto_16px] items-center gap-2.5 border-0 px-3.5 py-[9px] text-left text-footnote text-fg",
          "max-md:grid-cols-[16px_16px_1fr_auto_16px] max-md:gap-2 max-md:px-3 max-md:text-footnote",
          expandable ? "cursor-pointer hover:bg-surface" : "cursor-default",
          step.status === "running" && "bg-accent-soft",
        )}
      >
        <StatusIcon status={step.status} t={t} name={step.name} />
        <span className="grid place-items-center text-accent">
          <svg viewBox="0 0 16 16" width="13" height="13">
            {TOOL_ICONS[step.name]}
          </svg>
        </span>
        {/* 日本語の名前を主に、ツール名は小さく添える */}
        <span className="inline-flex min-w-0 items-center gap-1.5 text-footnote font-semibold text-fg">
          <span className="truncate">{step.label || step.name}</span>
          {isBySystem(step) && <AutoBadge t={t} />}
        </span>
        <span className="font-mono text-mini text-muted-2 max-md:hidden">{step.label ? step.name : ""}</span>
        <span className="min-w-0 truncate text-footnote text-muted max-md:hidden">{step.summary}</span>
        <span className="font-mono text-caption tabular-nums text-muted">{stepDurationLabel(step)}</span>
        {expandable ? (
          <span className={cn("text-muted transition-transform", expanded && "rotate-180")}>
            <svg viewBox="0 0 16 16" width="11" height="11">
              <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        ) : (
          <span aria-hidden className="block h-[11px] w-[11px]" />
        )}
      </button>
      {expandable && expanded && !hasChildren && (
        <div className="flex flex-col gap-2.5 border-t-[0.5px] border-dashed border-divider bg-surface px-3.5 pb-3.5 pl-10 pt-2 max-md:pl-3.5">
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

export function ToolStepTimeline({ step, expanded, onToggle, isLast, t, hasChildren = false }: { step: ToolCall; expanded: boolean; onToggle: () => void; isLast: boolean; t: Dictionary; hasChildren?: boolean }) {
  const expandable = hasChildren || isExpandable(step);
  const showInput = !hasChildren && hasInputData(step.input);
  const showOutput = !hasChildren && step.output != null;
  return (
    <div className="grid grid-cols-[22px_1fr]">
      <div className="grid grid-rows-[auto_1fr] items-start justify-items-center pt-0.5">
        <div className="grid h-[22px] w-[22px] place-items-center bg-surface-2">
          <StatusIcon status={step.status} t={t} name={step.name} />
        </div>
        {!isLast && <div className="min-h-4 w-[1.5px] flex-1 bg-divider-strong" />}
      </div>
      <div className="min-w-0 pb-3 pl-1">
        <button
          type="button"
          onClick={expandable ? onToggle : undefined}
          aria-expanded={expandable ? expanded : undefined}
          className={cn(
            "flex w-full items-center gap-2.5 border-0 bg-transparent py-0.5 text-left text-fg",
            expandable ? "cursor-pointer" : "cursor-default",
          )}
        >
          <span className="font-mono text-caption font-semibold text-fg">{step.name}</span>
          {isBySystem(step) && <AutoBadge t={t} />}
          <span className="min-w-0 flex-1 truncate text-footnote text-muted">{step.summary}</span>
          <span className="font-mono text-caption tabular-nums text-muted">{stepDurationLabel(step)}</span>
        </button>
        {expandable && expanded && !hasChildren && (
          <div className="flex flex-col gap-2 pt-2">
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
    </div>
  );
}

export function ToolStepLog({ steps, dict }: { steps: ToolCall[]; dict: Dictionary }) {
  const lines: { t: number; name: string; msg: string; kind: string }[] = [];
  let t = 0;
  steps.forEach((s) => {
    const start = t;
    const logName = (s.parentId ? "› " : "") + s.name;
    lines.push({ t: start, name: logName, msg: "started", kind: "start" });
    const keys = Object.keys(s.input);
    if (keys.length) {
      const k = keys[0];
      const v = s.input[k];
      lines.push({ t: start, name: logName, msg: `${k}: ${typeof v === "string" ? `"${v}"` : JSON.stringify(v)}`, kind: "param" });
    }
    if (s.status === "done") {
      lines.push({ t: start + s.durationMs, name: logName, msg: `done in ${formatMs(s.durationMs)} · ${s.summary}`, kind: "done" });
      const out = (s.output ?? {}) as Record<string, unknown>;
      const dt = start + s.durationMs;
      if ((s.name === "vector_search" || s.name === "bm25_search") && Array.isArray(out.hits)) {
        const hits = out.hits as { title: string; heading: string; score: number }[];
        hits.slice(0, LOG_DETAIL_MAX).forEach((h) =>
          lines.push({ t: dt, name: "", msg: `${h.score.toFixed(2)}  ${h.title}${h.heading ? ` — ${h.heading}` : ""}`, kind: "detail" }));
        if (hits.length > LOG_DETAIL_MAX)
          lines.push({ t: dt, name: "", msg: interpolate(dict.chat.moreItems, { n: hits.length - LOG_DETAIL_MAX }), kind: "detail" });
      } else if (s.name === "rerank" && Array.isArray(out.selected)) {
        const sel = out.selected as { score: number; title: string }[];
        sel.slice(0, LOG_DETAIL_MAX).forEach((h) =>
          lines.push({ t: dt, name: "", msg: `${h.score.toFixed(2)}  ${h.title}`, kind: "detail" }));
        if (sel.length > LOG_DETAIL_MAX)
          lines.push({ t: dt, name: "", msg: interpolate(dict.chat.moreItems, { n: sel.length - LOG_DETAIL_MAX }), kind: "detail" });
      }
      t = start + s.durationMs;
    } else if (s.status === "running") {
      lines.push({ t: start + (s.durationMs || 0), name: logName, msg: "streaming…", kind: "running" });
    }
  });
  const fmtT = (ms: number) => `+${Math.floor(ms / 1000).toString().padStart(2, "0")}.${(ms % 1000).toString().padStart(3, "0").slice(0, 3)}`;

  return (
    <div className="max-h-80 overflow-y-auto bg-code-bg px-4 pb-3.5 pt-2.5 font-mono text-caption leading-[1.65] text-fg-2 max-md:max-h-[260px] max-md:px-3 max-md:text-mini">
      {lines.map((l, i) => (
        <div key={i} className="flex gap-3 py-px">
          <span className="shrink-0 text-muted-2">{fmtT(l.t)}</span>
          <span className={cn("min-w-[110px] shrink-0 max-md:min-w-[90px]", l.kind === "done" ? "text-accent" : "text-accent")}>{l.name}</span>
          <span
            className={cn(
              "min-w-0 flex-1 break-words",
              l.kind === "done" ? "text-fg" : l.kind === "param" ? "text-muted" : l.kind === "running" ? "text-accent" : l.kind === "detail" ? "text-muted-2" : "text-fg-2",
            )}
          >
            {l.msg}
          </span>
        </div>
      ))}
    </div>
  );
}
