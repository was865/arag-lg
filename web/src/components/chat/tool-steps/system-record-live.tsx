"use client";
/**
 * 出典の面の社内システムの記録に「最新にする」を付ける（specs/033 R17）。
 * 同じ利用者・同じツール・同じ引数で呼び直し、前の値との差を印で示す。回答の文は変えない。
 * 呼び直しはメッセージの記録（システムの処理 mcp_refresh）にも残る（api が足す）。
 */
import { useState } from "react";
import type { Dictionary } from "@/i18n/dictionary";
import { interpolate } from "@/i18n/interpolate";
import { chatApi } from "@/lib/chat/api";
import { changeViews, type ChangeView } from "@/lib/chat/system-changes";
import { formatFetchedAt } from "@/lib/datetime";
import type { SystemRecord } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { recordFromOutput, SystemRecordView } from "./system-record";

interface Fresh {
  record: SystemRecord | null;
  changes: ChangeView[];
  error: string | null;
  at: string;
}

function Arrow({ dir }: { dir: ChangeView["dir"] }) {
  if (!dir) return null;
  return <span aria-hidden className={dir === "up" ? "text-fg" : "text-danger"}>{dir === "up" ? "↑" : "↓"}</span>;
}

export function ChangeList({ changes, t }: { changes: ChangeView[]; t: Dictionary }) {
  if (changes.length === 0) return null;
  return (
    <ul className="m-0 list-none space-y-0.5 p-0 text-footnote">
      {changes.map((c, i) => (
        <li key={`${c.key}-${c.column ?? c.kind}-${i}`} className="flex flex-wrap items-baseline gap-x-1.5">
          <span className="font-mono text-caption text-muted">{c.key}</span>
          {c.kind === "value" ? (
            <>
              <span className="text-muted">{c.column}</span>
              <span className="text-muted line-through">{c.before}</span>
              <span>→</span>
              <span className="font-semibold">{c.after}</span>
              <Arrow dir={c.dir} />
            </>
          ) : (
            <span className="text-muted">{c.kind === "added" ? t.chat.systemRowAdded : t.chat.systemRowRemoved}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

export function SystemRecordLive({
  record,
  messageId,
  sectionId,
  t,
}: {
  record: SystemRecord;
  messageId?: string;
  sectionId: string;
  t: Dictionary;
}) {
  const [busy, setBusy] = useState(false);
  const [fresh, setFresh] = useState<Fresh | null>(null);

  const refresh = async () => {
    if (!messageId || busy) return;
    setBusy(true);
    try {
      const out = await chatApi.refreshRecord(messageId, sectionId);
      const rec = out.record ? recordFromOutput(out.record as Record<string, unknown>) : null;
      setFresh({
        record: rec,
        changes: changeViews(out.changes),
        error: out.error ?? null,
        at: rec?.fetchedAt ?? new Date().toISOString(),
      });
    } catch (e) {
      setFresh({ record: null, changes: [], error: e instanceof Error ? e.message : String(e), at: new Date().toISOString() });
    } finally {
      setBusy(false);
    }
  };

  const shown = fresh?.record ?? record;
  return (
    <div className="space-y-2">
      {messageId && (
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" size="sm" onClick={() => void refresh()} disabled={busy} title={t.chat.systemRefreshTitle}>
            {busy && <Spinner size="xs" />}
            {busy ? t.chat.systemRefreshing : t.chat.systemRefresh}
          </Button>
          {fresh && (
            <span className={fresh.error ? "text-caption text-danger" : "text-caption text-muted"}>
              {fresh.error
                ? interpolate(t.chat.systemRefreshFailed, { error: fresh.error })
                : interpolate(fresh.changes.length ? t.chat.systemRefreshChanged : t.chat.systemRefreshSame, {
                    at: formatFetchedAt(fresh.at),
                    n: String(fresh.changes.length),
                  })}
            </span>
          )}
        </div>
      )}
      {fresh && !fresh.error && <ChangeList changes={fresh.changes} t={t} />}
      <SystemRecordView record={shown} t={t} />
      {fresh?.record && (
        <div className="text-caption text-muted">
          {interpolate(t.chat.systemAnsweredAt, { at: formatFetchedAt(record.fetchedAt) })}
        </div>
      )}
    </div>
  );
}
