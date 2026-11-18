/** 各ツールの段階の「出力」の表示。 */
import { parseRetrieveHits } from "@/lib/chat/evidence";
import { cn } from "@/lib/utils";
import { Icon } from "@/components/icons";
import type { RerankHit, ToolCall } from "@/lib/types";
import { interpolate } from "@/i18n/interpolate";
import type { Dictionary } from "@/i18n/dictionary";
import { CandidateHit, ExpandedHit, GradeCandidate, KeyValueGrid, VERIFY_DETAIL_MAX, VerifyDetail, boxCls, hasTokenUsage, preCls, sectionLabelCls, tokenRows, verifyVerdictChipClass, verifyVerdictLabel } from "./shared";
import { SystemFields } from "./system-fields";
import { TableResult } from "./table-result";

export function VerifyDetailRow({ detail, index, t }: { detail: VerifyDetail; index: number; t: Dictionary }) {
  const citedNums = Array.isArray(detail.citedNums) ? detail.citedNums : [];
  const verdict = detail.verdict === "supported" || detail.verdict === "unsupported" || detail.verdict === "not_a_claim" || detail.verdict === "unverified"
    ? detail.verdict
    : "not_a_claim";
  return (
    <div className={cn("px-3 py-2.5", index > 0 && "border-t-[0.5px] border-divider")}>
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className={cn(
          "rounded-full px-2 py-px text-mini font-semibold",
          verifyVerdictChipClass(verdict),
        )}>
          {verifyVerdictLabel(verdict, t)}
        </span>
        {citedNums.length > 0 && (
          <span className="font-mono text-mini text-muted-2">
            {t.chat.verifyCitations}: {citedNums.map((n) => `[${n}]`).join(" ")}
          </span>
        )}
      </div>
      <div className="mt-1 whitespace-pre-wrap break-words text-footnote leading-[1.5] text-fg-2">
        {detail.text}
      </div>
      {detail.reason && (
        <div className="mt-1 whitespace-pre-wrap break-words font-mono text-mini leading-[1.5] text-muted-2">
          {t.chat.verifyReason}: {detail.reason}
        </div>
      )}
    </div>
  );
}

export function ToolOutputBlock({ step, t }: { step: ToolCall; t: Dictionary }) {
  const output = step.output;
  if (!output) return null;

  if (step.name === "answer") {
    return hasTokenUsage(output) ? <KeyValueGrid rows={tokenRows(output, t)} /> : null;
  }

  if (step.name === "read_image") {
    // 画像から読み取った文章（失敗時は理由）
    const text = typeof output.description === "string" ? output.description : typeof output.error === "string" ? output.error : "";
    return text ? <pre className={preCls}>{text}</pre> : null;
  }

  if (step.name === "reasoning") {
    return (
      typeof output.reasoning === "string" && output.reasoning.length > 0
        ? <pre className={preCls}>{output.reasoning}</pre>
        : null
    );
  }

  if (step.name === "rerank" && Array.isArray(output.selected)) {
    return (
      <div className="flex flex-col gap-[5px] py-1">
        {(output.selected as RerankHit[]).map((s) => (
          <div
            key={s.id}
            className="grid grid-cols-[80px_42px_1fr] items-center gap-2.5 text-caption max-md:grid-cols-[90px_38px_1fr] max-md:gap-2"
          >
            <div className="h-[5px] overflow-hidden rounded-full bg-divider">
              <span className="block h-full rounded-full bg-accent" style={{ width: `${s.score * 100}%` }} />
            </div>
            <span className="font-mono text-caption font-semibold text-accent">{s.score.toFixed(2)}</span>
            <span className="truncate text-fg-2">{s.title}</span>
          </div>
        ))}
      </div>
    );
  }
  if ((step.name === "vector_search" || step.name === "bm25_search" || step.name === "retrieve" || step.name === "candidates") && Array.isArray(output.hits)) {
    const hits = output.hits as CandidateHit[];
    if (hits.length === 0) {
      if (output.fallback) {
        const terms = Array.isArray(output.terms)
          ? (output.terms as unknown[]).map(String)
          : String(step.input.query ?? "").split(/\s+/).filter(Boolean);
        return (
          <div className="flex items-start gap-1.5 rounded-control bg-surface-2 px-2.5 py-2 text-caption leading-[1.6] text-fg-2">
            <Icon name="info" size={12} className="mt-[3px] shrink-0 text-muted" />
            <span>
              {interpolate(output.fallback === "codes" ? t.chat.keywordRelax : t.chat.keywordFallback, {
                terms: terms.map((x) => `「${x}」`).join(""),
              })}
            </span>
          </div>
        );
      }
      return <div className="px-1 py-1 text-caption text-muted">{t.chat.noCandidates}</div>;
    }
    // スコアは非負前提（dense=cosine, sparse=BM25/dot）。リスト内最大値でバー幅を正規化。
    const max = Math.max(...hits.map((h) => h.score), 1e-9);
    return (
      <div className="flex max-h-72 flex-col gap-[5px] overflow-y-auto py-1">
        {hits.map((h, i) => (
          <div
            key={i}
            className="grid grid-cols-[64px_42px_1fr] items-center gap-2.5 text-caption max-md:grid-cols-[54px_38px_1fr] max-md:gap-2"
          >
            <div className="h-[5px] overflow-hidden rounded-full bg-divider">
              <span className="block h-full rounded-full bg-accent" style={{ width: `${Math.max(4, (h.score / max) * 100)}%` }} />
            </div>
            <span className="font-mono text-caption font-semibold text-accent">{h.score.toFixed(2)}</span>
            <span className="truncate text-fg-2">
              <span className="text-fg">{h.title}</span>
              {h.heading && <span className="text-muted-2"> — {h.heading}</span>}
            </span>
          </div>
        ))}
      </div>
    );
  }
  if (step.name === "embed") {
    return <KeyValueGrid rows={[{ k: "dims", v: String(output.dims ?? "—") }]} />;
  }
  if (step.name === "expand") {
    const expanded = Array.isArray(output.expanded) ? (output.expanded as ExpandedHit[]) : [];
    if (expanded.length === 0) {
      return <KeyValueGrid rows={[{ k: t.chat.expandCount, v: String(output.count ?? 0) }]} />;
    }
    return (
      <div className="flex flex-col gap-2">
        <KeyValueGrid rows={[{ k: t.chat.expandCount, v: String(output.count ?? expanded.length) }]} />
        <div className="overflow-hidden rounded-control border-[0.5px] border-divider bg-code-bg">
          {expanded.map((h, i) => (
            <div key={`${h.id}-${i}`} className={cn("px-3 py-2.5", i > 0 && "border-t-[0.5px] border-divider")}>
              <div className="flex min-w-0 items-center gap-2">
                <span className="font-mono text-caption font-semibold tabular-nums text-accent">{h.score.toFixed(2)}</span>
                <span className="min-w-0 flex-1 truncate text-footnote font-medium text-fg">{h.title}</span>
                <span className="shrink-0 font-mono text-mini text-muted-2">p.{h.page}</span>
                <span className="shrink-0 font-mono text-mini text-muted-2">{h.expandedChars}ch</span>
              </div>
              {h.heading && <div className="mt-0.5 truncate font-mono text-mini text-muted-2">{h.heading}</div>}
              {h.preview && <div className="mt-1 line-clamp-2 whitespace-pre-wrap text-caption leading-[1.5] text-fg-2">{h.preview}</div>}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (step.name === "grade") {
    const candidates = Array.isArray(output.candidates) ? (output.candidates as GradeCandidate[]) : [];
    if (candidates.length === 0) return <pre className={preCls}>{JSON.stringify(output, null, 2)}</pre>;
    return (
      <div className="flex flex-col gap-2">
        <KeyValueGrid rows={[
          { k: "kept", v: `${String(output.kept ?? 0)} / ${String(output.total ?? candidates.length)}` },
          { k: "retry", v: output.needRetry ? "yes" : "no" },
        ]} />
        <div className="overflow-hidden rounded-control border-[0.5px] border-divider bg-code-bg">
          {candidates.map((c, i) => (
            <div key={`${c.chunkId}-${i}`} className={cn("grid grid-cols-[58px_42px_1fr] items-start gap-2.5 px-3 py-2.5 text-caption", i > 0 && "border-t-[0.5px] border-divider")}>
              <span className={cn("rounded-full px-2 py-px text-center text-mini font-semibold", c.kept ? "bg-accent-soft text-accent" : "bg-divider text-muted")}>
                {c.kept ? "kept" : "skip"}
              </span>
              <span className="font-mono text-caption font-semibold tabular-nums text-accent">{c.score.toFixed(2)}</span>
              <span className="min-w-0">
                <span className="block truncate text-fg">{c.title}</span>
                {c.heading && <span className="block truncate font-mono text-mini text-muted-2">{c.heading}</span>}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if ((step.name === "retrieve" || step.name === "fetch_document") && typeof output.result === "string") {
    const hits = parseRetrieveHits(output.result);
    if (hits.length) {
      return (
        <div className="overflow-hidden rounded-control border-[0.5px] border-divider bg-code-bg">
          {hits.map((h, i) => (
            <div
              key={`${h.n}-${i}`}
              className={cn(
                "grid grid-cols-[28px_1fr] gap-2 px-3 py-2.5",
                i > 0 && "border-t-[0.5px] border-divider",
              )}
            >
              <span className="pt-px font-mono text-caption font-semibold text-accent">[{h.n}]</span>
              <div className="min-w-0">
                <div className="truncate text-footnote font-medium text-fg">{h.title}</div>
                <div className="truncate font-mono text-mini text-muted-2">{h.heading}</div>
                {h.snippet && (
                  <div className="mt-1 line-clamp-3 whitespace-pre-wrap text-caption leading-[1.5] text-fg-2">
                    {h.snippet}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      );
    }
    // パースに失敗（"該当する資料は見つかりませんでした。" 等）した場合は本文をそのまま見せる。
    return (
      <div className="rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 text-footnote leading-[1.55] text-fg-2">
        {output.result}
      </div>
    );
  }

  if (step.name === "verify") {
    const claims = Array.isArray(output.claims) ? (output.claims as string[]) : [];
    const details = Array.isArray(output.details) ? (output.details as VerifyDetail[]) : [];
    const verifyError = typeof output.verifyError === "string" ? output.verifyError : "";
    const message = verifyError ? t.chat.verifyFailed : output.checkableClaims === 0 ? t.chat.noCheckableClaims : t.chat.allGrounded;
    const detailBlock = details.length > 0 && (
      <div>
        <div className={sectionLabelCls}>{t.chat.sectionVerifyDetails}</div>
        <div className="overflow-hidden rounded-control border-[0.5px] border-divider bg-code-bg">
          {details.slice(0, VERIFY_DETAIL_MAX).map((detail, i) => (
            <VerifyDetailRow key={`${detail.verdict}-${i}`} detail={detail} index={i} t={t} />
          ))}
          {details.length > VERIFY_DETAIL_MAX && (
            <div className="border-t-[0.5px] border-divider px-3 py-2.5 text-caption text-muted-2">
              {interpolate(t.chat.moreItems, { n: details.length - VERIFY_DETAIL_MAX })}
            </div>
          )}
        </div>
      </div>
    );
    if (claims.length === 0) {
      return (
        <div className="flex flex-col gap-2">
          {hasTokenUsage(output) && <KeyValueGrid rows={tokenRows(output, t)} />}
          <div className="rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 text-footnote leading-[1.55] text-fg-2">
            {message}
            {verifyError && <div className="mt-1 font-mono text-mini text-muted-2">{verifyError}</div>}
          </div>
          {detailBlock}
        </div>
      );
    }
    return (
      <div className="flex flex-col gap-2">
        {hasTokenUsage(output) && <KeyValueGrid rows={tokenRows(output, t)} />}
        <ul className="flex flex-col gap-1.5 rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5">
          {claims.map((c, i) => (
            <li key={i} className="grid grid-cols-[14px_1fr] gap-2 text-footnote leading-[1.5] text-fg-2">
              <span className="pt-px text-center font-mono text-caption font-semibold text-danger">!</span>
              <span className="min-w-0 whitespace-pre-wrap break-words">{c}</span>
            </li>
          ))}
        </ul>
        {detailBlock}
      </div>
    );
  }

  if (step.name === "revise") {
    return (
      <div className="flex flex-col gap-2">
        {hasTokenUsage(output) && <KeyValueGrid rows={tokenRows(output, t)} />}
        {typeof output.draft === "string" && (
          <div>
            <div className={sectionLabelCls}>{t.chat.sectionDraft}</div>
            <div className="whitespace-pre-wrap break-words rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 text-footnote leading-[1.55] text-muted">
              {output.draft}
            </div>
          </div>
        )}
        {typeof output.revised === "string" && (
          <div>
            <div className={sectionLabelCls}>{t.chat.sectionRevised}</div>
            <div className="whitespace-pre-wrap break-words rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 text-footnote leading-[1.55] text-fg-2">
              {output.revised}
            </div>
          </div>
        )}
      </div>
    );
  }

  if (step.name === "system") return <SystemFields data={output} t={t} />;

  if (step.name === "understand") {
    const queries = Array.isArray(output.queries) ? (output.queries as unknown[]).map(String) : [];
    const chip = "rounded-full border-[0.5px] border-divider-strong bg-surface px-2 py-0.5 text-caption text-fg-2";
    return (
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={chip}>{output.kind === "chat" ? t.chat.understandKindChat : t.chat.understandKindDocs}</span>
          {output.table === true && <span className={chip}>{t.chat.understandTable}</span>}
        </div>
        {queries.length > 0 && (
          <div>
            <div className={sectionLabelCls}>{t.chat.understandQueries}</div>
            <ol className="m-0 list-none space-y-1 p-0">
              {queries.map((q, i) => (
                <li key={i} className={cn(boxCls, "flex gap-2 py-1.5")}>
                  <span className="font-mono text-caption text-muted-2">{i + 1}</span>
                  <span className="min-w-0 break-words text-fg">{q}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
        {typeof output.error === "string" && (
          <div className="text-caption text-muted">
            {t.chat.understandError}（{output.error}）
          </div>
        )}
      </div>
    );
  }

  if (step.name === "table_query" && typeof output.result === "string") {
    return <TableResult output={output} t={t} />;
  }

  if (step.name === "review" && typeof output.note === "string") {
    const next = Array.isArray(output.next_tools) ? (output.next_tools as unknown[]).map(String) : [];
    return (
      <div className="space-y-2">
        <div>
          <div className={sectionLabelCls}>{t.chat.reviewNote}</div>
          <div className="whitespace-pre-wrap break-words rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 text-footnote leading-[1.55] text-fg-2">
            {output.note}
          </div>
        </div>
        <KeyValueGrid rows={[{ k: t.chat.reviewNext, v: next.length ? next.join("・") : t.chat.reviewRewrote }]} />
        {typeof output.error === "string" && <pre className={preCls}>{output.error}</pre>}
      </div>
    );
  }

  // work_calendar は整形済みの事実テキスト（{result:"..."}）。そのまま可読表示する。
  if (step.name === "work_calendar" && typeof output.result === "string") {
    return (
      <div className="whitespace-pre-wrap break-words rounded-control border-[0.5px] border-divider bg-code-bg px-3 py-2.5 text-footnote leading-[1.55] text-fg-2">
        {output.result}
      </div>
    );
  }

  return <pre className={preCls}>{JSON.stringify(output, null, 2)}</pre>;
}
