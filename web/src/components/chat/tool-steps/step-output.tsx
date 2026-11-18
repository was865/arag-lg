/** 各ツールの段階の「出力」の表示。種類ごとの中身は output-search（検索系）・output-checks（確かめる系）にある。 */
import type { ToolCall } from "@/lib/types";
import type { Dictionary } from "@/i18n/dictionary";
import { cn } from "@/lib/utils";
import { KeyValueGrid, boxCls, hasTokenUsage, preCls, tokenRows } from "./shared";
import { ExpandOutput, GradeOutput, HitsOutput, RerankOutput, RetrievedOutput } from "./output-search";
import { ReviewOutput, ReviseOutput, UnderstandOutput, VerifyOutput } from "./output-checks";
import { SystemFields } from "./system-fields";
import { TableResult } from "./table-result";
import type { RerankHit } from "@/lib/types";

const SEARCH_HITS = new Set(["vector_search", "bm25_search", "retrieve", "candidates"]);

export function ToolOutputBlock({ step, t }: { step: ToolCall; t: Dictionary }) {
  const output = step.output;
  if (!output) return null;
  const text = (v: unknown) => (typeof v === "string" ? v : null);

  switch (step.name) {
    case "answer":
      return hasTokenUsage(output) ? <KeyValueGrid rows={tokenRows(output, t)} /> : null;
    case "read_image": {
      // 画像から読み取った文章（失敗時は理由）
      const s = text(output.description) ?? text(output.error) ?? "";
      return s ? <pre className={preCls}>{s}</pre> : null;
    }
    case "reasoning":
      return text(output.reasoning) ? <pre className={preCls}>{text(output.reasoning)}</pre> : null;
    case "embed":
      return <KeyValueGrid rows={[{ k: "dims", v: String(output.dims ?? "—") }]} />;
    case "expand":
      return <ExpandOutput output={output} t={t} />;
    case "grade":
      return <GradeOutput output={output} />;
    case "verify":
      return <VerifyOutput output={output} t={t} />;
    case "revise":
      return <ReviseOutput output={output} t={t} />;
    case "system":
      return <SystemFields data={output} t={t} />;
    case "understand":
      return <UnderstandOutput output={output} t={t} />;
  }
  if (step.name === "rerank" && Array.isArray(output.selected)) return <RerankOutput selected={output.selected as RerankHit[]} />;
  if (SEARCH_HITS.has(step.name) && Array.isArray(output.hits)) return <HitsOutput step={step} output={output} t={t} />;
  const result = text(output.result);
  if ((step.name === "retrieve" || step.name === "fetch_document") && result !== null) return <RetrievedOutput result={result} />;
  if (step.name === "table_query" && result !== null) return <TableResult output={output} t={t} />;
  if (step.name === "review" && typeof output.note === "string") return <ReviewOutput output={output} t={t} />;
  // work_calendar は整形済みの事実テキスト（{result:"..."}）。そのまま可読表示する。
  if (step.name === "work_calendar" && result !== null) return <div className={cn(boxCls, "whitespace-pre-wrap break-words")}>{result}</div>;
  return <pre className={preCls}>{JSON.stringify(output, null, 2)}</pre>;
}
