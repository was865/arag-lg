/** 確かめる系の段階の出力（質問の理解・根拠の確認・書き直し・見直し）。 */
import { cn } from "@/lib/utils";
import { interpolate } from "@/i18n/interpolate";
import type { Dictionary } from "@/i18n/dictionary";
import { KeyValueGrid, VERIFY_DETAIL_MAX, VerifyDetail, boxCls, hasTokenUsage, preCls, sectionLabelCls, tokenRows, verifyVerdictChipClass, verifyVerdictLabel } from "./shared";

type Out = Record<string, unknown>;

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

/** 根拠の確認（言い切りの点検） */
export function VerifyOutput({ output, t }: { output: Out; t: Dictionary }) {
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
        <div className={boxCls}>
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

/** 書き直し（下書き → 直した文） */
export function ReviseOutput({ output, t }: { output: Out; t: Dictionary }) {
  return (
    <div className="flex flex-col gap-2">
      {hasTokenUsage(output) && <KeyValueGrid rows={tokenRows(output, t)} />}
      {typeof output.draft === "string" && (
        <div>
          <div className={sectionLabelCls}>{t.chat.sectionDraft}</div>
          <div className={cn(boxCls, "whitespace-pre-wrap break-words text-muted")}>
            {output.draft}
          </div>
        </div>
      )}
      {typeof output.revised === "string" && (
        <div>
          <div className={sectionLabelCls}>{t.chat.sectionRevised}</div>
          <div className={cn(boxCls, "whitespace-pre-wrap break-words")}>
            {output.revised}
          </div>
        </div>
      )}
    </div>
  );
}

/** 質問の理解（種類・表か・検索に使う言い換え） */
export function UnderstandOutput({ output, t }: { output: Out; t: Dictionary }) {
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

/** 見直し（気づいた点と次の手） */
export function ReviewOutput({ output, t }: { output: Out; t: Dictionary }) {
  const next = Array.isArray(output.next_tools) ? (output.next_tools as unknown[]).map(String) : [];
  return (
    <div className="space-y-2">
      <div>
        <div className={sectionLabelCls}>{t.chat.reviewNote}</div>
        <div className={cn(boxCls, "whitespace-pre-wrap break-words")}>
          {String(output.note)}
        </div>
      </div>
      <KeyValueGrid rows={[{ k: t.chat.reviewNext, v: next.length ? next.join("・") : t.chat.reviewRewrote }]} />
      {typeof output.error === "string" && <pre className={preCls}>{output.error}</pre>}
    </div>
  );
}
