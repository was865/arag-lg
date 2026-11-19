/** 各ツールの段階の「入力」の表示。 */
import { cn } from "@/lib/utils";
import type { ToolCall } from "@/lib/types";
import type { Dictionary } from "@/i18n/dictionary";
import { KeyValueGrid, ModelBlock, boxCls, preCls, sectionLabelCls } from "./shared";
import { SystemFields } from "./system-fields";

export function ToolInputBlock({ step, t }: { step: ToolCall; t: Dictionary }) {
  if ((step.name === "reasoning" || step.name === "answer") && typeof step.input.model === "string") {
    return <ModelBlock model={step.input.model} />;
  }
  if ((step.name === "verify" || step.name === "revise") && typeof step.input.model === "string") {
    return <ModelBlock model={step.input.model} />;
  }
  // 聞き返し（specs/031）: 問いと選択肢を読める形で
  if (step.name === "system" || step.name === "ask_user") return <SystemFields data={step.input} t={t} />;
  if (step.name === "understand" && typeof step.input.question === "string") {
    return <div className={cn(boxCls, "whitespace-pre-wrap break-words")}>{step.input.question}</div>;
  }
  if (step.name === "table_query") {
    const code = (v: unknown) => <code className="font-mono text-caption text-fg">{String(v)}</code>;
    const rows = [
      { k: t.chat.tableSource, v: `[${String(step.input.source ?? "")}]` },
      { k: t.chat.tableWhere, v: step.input.where ? code(step.input.where) : t.chat.tableAll },
    ];
    if (step.input.compute) rows.push({ k: t.chat.tableCompute, v: code(step.input.compute) });
    return <KeyValueGrid rows={rows} />;
  }
  if (step.name === "review") {
    // 差し戻した下書きを丸ごと見せる（回答の欄からは消えるが、記録には残す）
    const rows: { k: string; v: React.ReactNode }[] = [];
    if (typeof step.input.trigger === "string") rows.push({ k: t.chat.reviewTrigger, v: `「${step.input.trigger}」` });
    if (typeof step.input.searches === "number") rows.push({ k: t.chat.reviewSearches, v: String(step.input.searches) });
    return (
      <div className="space-y-2">
        {rows.length > 0 && <KeyValueGrid rows={rows} />}
        {typeof step.input.draft === "string" && (
          <div>
            <div className={sectionLabelCls}>{t.chat.reviewDraft}</div>
            <div className="max-h-64 overflow-y-auto whitespace-pre-wrap break-words rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 text-footnote leading-[1.55] text-fg-2">
              {step.input.draft.trim()}
            </div>
          </div>
        )}
      </div>
    );
  }
  if (step.name === "retrieve" && typeof step.input.query === "string") {
    return (
      <div className="rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5">
        <div className="eyebrow mb-1 font-mono">query</div>
        <div className="text-footnote leading-[1.5] text-fg">{step.input.query}</div>
      </div>
    );
  }
  if (step.name === "fetch_document") {
    const ref = step.input.ref;
    const document = step.input.document;
    return (
      <div className="space-y-[3px] rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 font-mono text-caption leading-[1.6] text-fg-2">
        {ref != null && (
          <div>
            <span className="text-muted-2">{t.chat.sourceLabel}</span>
            <span className="text-fg">[{String(ref)}]</span>
          </div>
        )}
        {document != null && (
          <div>
            <span className="text-muted-2">{t.chat.documentLabel}</span>
            <span className="text-fg">{String(document)}</span>
          </div>
        )}
      </div>
    );
  }
  if (step.name === "vector_search" || step.name === "bm25_search") {
    const rows: { k: string; v: React.ReactNode }[] = [];
    if (typeof step.input.mode === "string") rows.push({ k: "mode", v: step.input.mode });
    return (
      <div className="space-y-2">
        {rows.length > 0 && <KeyValueGrid rows={rows} />}
        {typeof step.input.query === "string" && (
          <div className="rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5">
            <div className="eyebrow mb-1 font-mono">query</div>
            <div title={step.input.query} className="line-clamp-3 break-words text-footnote leading-[1.5] text-fg [overflow-wrap:anywhere]">{step.input.query}</div>
          </div>
        )}
      </div>
    );
  }
  if (step.name === "rerank") {
    const rows: { k: string; v: React.ReactNode }[] = [];
    if (step.input.model != null) rows.push({ k: "model", v: String(step.input.model) });
    if (step.input.candidates != null) rows.push({ k: "candidates", v: String(step.input.candidates) });
    if (step.input.top_n != null) rows.push({ k: "top_n", v: String(step.input.top_n) });
    if (rows.length) return <KeyValueGrid rows={rows} />;
  }
  if (step.name === "embed" && step.input.model != null) {
    return <KeyValueGrid rows={[{ k: "model", v: String(step.input.model) }]} />;
  }
  return <pre className={preCls}>{JSON.stringify(step.input, null, 2)}</pre>;
}
