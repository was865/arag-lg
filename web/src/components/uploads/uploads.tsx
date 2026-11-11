"use client";

import { AnimatePresence, m } from "motion/react";
import { DURATION, EASE } from "@/lib/motion";
import { useState } from "react";
import { Icon } from "@/components/icons";
import { IconButton } from "@/components/ui/button";
import { getFileMeta } from "@/lib/file-types";
import { cn, formatFileSize } from "@/lib/utils";
import type { IngestStage, StagedFile } from "@/lib/types";
import { uploadActionFor } from "@/hooks/use-uploads";
import { useT } from "@/i18n/context";
import { interpolate } from "@/i18n/interpolate";

/** 解析→チャンク化→埋め込み→索引化 の段階ステッパー。SSE の stage で現在位置を点灯する。 */
function IngestStepper({ stage }: { stage?: IngestStage }) {
  const { t } = useT();
  const STAGES: { key: IngestStage; label: string }[] = [
    { key: "parsing", label: t.uploads.stageParsing },
    { key: "chunking", label: t.uploads.stageChunking },
    { key: "embedding", label: t.uploads.stageEmbedding },
    { key: "indexing", label: t.uploads.stageIndexing },
  ];
  // 現在段階のインデックス（ready は全完了扱い、未取得は先頭手前）。
  const active = stage === "ready" ? STAGES.length : stage ? STAGES.findIndex((s) => s.key === stage) : 0;
  return (
    <div className="mt-1.5 flex items-center gap-1">
      {STAGES.map((s, i) => {
        const done = i < active;
        const current = i === active;
        return (
          <div key={s.key} className="flex flex-1 items-center gap-1">
            <span
              className={cn(
                "h-[3px] flex-1 rounded-full transition-colors duration-300",
                done && "bg-accent",
                current && "animate-soft-pulse bg-accent",
                !done && !current && "bg-divider",
              )}
            />
            <span
              className={cn(
                "shrink-0 text-mini font-semibold tracking-[0.02em] transition-colors",
                done || current ? "text-accent" : "text-muted-2",
              )}
            >
              {s.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function AttachmentChip({ file, onRemove, onRetry }: { file: StagedFile; onRemove: (id: string) => void; onRetry?: (id: string) => void }) {
  const { t } = useT();
  const meta = getFileMeta(file.name);
  const ext = (file.name.split(".").pop() || "").toUpperCase();
  // 解析段階はファイル形式で表示（例: 「PDF 解析中」「XLSX 解析中」）。
  const processingText = file.stage === "parsing"
    ? interpolate(t.uploads.parsingFile, { ext })
    : file.stageDetail || t.uploads.processing;
  const elapsed = file.durationMs != null ? interpolate(t.uploads.durationSuffix, { n: (file.durationMs / 1000).toFixed(1) }) : null;
  return (
    <div
      className={cn(
        "relative flex items-center gap-2.5 rounded-control border-[0.5px] border-divider-strong bg-surface-2 py-2 pl-2 pr-2.5 transition-colors hover:bg-bg-2",
        file.status === "ready" && "border-accent bg-accent-soft",
        file.status === "error" && "border-[rgba(184,58,31,0.3)] bg-[rgba(184,58,31,0.08)]",
        file.status === "skipped" && "border-dashed opacity-60",
      )}
    >
      <span
        className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-control"
        style={{ background: meta.color + "20", color: meta.color }}
      >
        <Icon name={meta.iconName} size={14} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-footnote font-semibold text-fg" title={file.name}>
          {file.name}
        </div>
        <div className="mt-0.5 flex items-center gap-[5px] font-mono text-mini text-muted">
          {file.status === "uploading" && (
            <>
              <span className="h-[9px] w-[9px] shrink-0 animate-spin-fast rounded-full border-[1.5px] border-divider-strong border-t-accent" />
              <span>{interpolate(t.uploads.uploading, { progress: file.progress })}</span>
            </>
          )}
          {file.status === "queued" && (
            <>
              <span className="h-[9px] w-[9px] shrink-0 animate-spin-fast rounded-full border-[1.5px] border-divider-strong border-t-accent" />
              <span>{t.uploads.queued}</span>
            </>
          )}
          {file.status === "processing" && (
            <>
              <span className="h-[9px] w-[9px] shrink-0 animate-spin-fast rounded-full border-[1.5px] border-divider-strong border-t-accent" />
              <span>
                {processingText}
                {file.stage === "embedding" && file.chunks ? ` · ${interpolate(t.uploads.chunkSuffix, { n: file.chunks })}` : ""}
                {` · ${file.progress}%`}
              </span>
            </>
          )}
          {file.status === "ready" && (
            <>
              <span className="text-accent">✓</span>
              <span>
                {/* pages/chunks 都无值 = 非 KB 摄取的能力包附件（浏览器内解析），无“索引块”概念 */}
                {file.pages == null && file.chunks == null
                  ? interpolate(t.uploads.readyDetailPlain, { type: meta.label, size: formatFileSize(file.size) })
                  : interpolate(t.uploads.readyDetail, {
                      type: meta.label,
                      size: formatFileSize(file.size),
                      n: file.pages ?? file.chunks ?? 0,
                    })}
                {elapsed ? ` · ${elapsed}` : ""}
              </span>
            </>
          )}
          {file.status === "skipped" && (
            <>
              <span className="text-muted-2">⊘</span>
              {/* 重複スキップは専用文言、未対応形式は既定文言。error にスキップ理由を入れて出し分ける。 */}
              <span>{file.error ?? t.uploads.skippedStatus}</span>
            </>
          )}
          {file.status === "error" && (
            <>
              <span className="text-danger">!</span>
              <span>{file.error || t.uploads.errorFallback}</span>
              {onRetry && file.jobId && (
                <button
                  className="ml-1 rounded-[4px] border-0 bg-transparent px-1.5 py-0.5 text-mini font-semibold text-danger hover:bg-[rgba(184,58,31,0.12)]"
                  onClick={() => onRetry(file.id)}
                >
                  {t.uploads.retryButton}
                </button>
              )}
            </>
          )}
        </div>
        {file.status === "uploading" && (
          <div className="mt-1 h-[3px] overflow-hidden rounded-full bg-divider">
            <span className="block h-full rounded-full bg-accent transition-[width] duration-300 ease-out" style={{ width: `${file.progress}%` }} />
          </div>
        )}
        {file.status === "processing" && <IngestStepper stage={file.stage} />}
      </div>
      {uploadActionFor(file.status) !== "none" && (
        <IconButton size="icon-sm"
          onClick={() => onRemove(file.id)}
          label={uploadActionFor(file.status) === "remove" ? t.uploads.ariaRemove : t.uploads.ariaCancel}
        >
          <svg viewBox="0 0 12 12" width="10" height="10">
            <path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" />
          </svg>
        </IconButton>
      )}
    </div>
  );
}

export function AttachmentTray({ files, onRemove, onRetry }: { files: StagedFile[]; onRemove: (id: string) => void; onRetry?: (id: string) => void }) {
  if (!files.length) return null;
  return (
    <div className="flex max-h-[200px] flex-col gap-1.5 overflow-y-auto px-2 pt-2 max-md:max-h-[156px]">
      {files.map((f) => (
        <AttachmentChip key={f.id} file={f} onRemove={onRemove} onRetry={onRetry} />
      ))}
    </div>
  );
}

export function UserAttachments({ files }: { files: StagedFile[] }) {
  const { t } = useT();
  if (!files.length) return null;
  return (
    <div className="mb-1 rounded-card border-[0.5px] border-divider bg-surface-2 px-3 py-2.5">
      <div className="mb-2 flex items-center gap-1.5 text-mini font-semibold uppercase tracking-[0.05em] text-muted">
        <Icon name="paperclip" size={11} />
        {t.uploads.attachedFiles}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {files.map((f) => {
          const meta = getFileMeta(f.name);
          return (
            <span key={f.id} className="inline-flex items-center gap-2 rounded-full border-[0.5px] border-divider-strong bg-surface py-[5px] pl-[5px] pr-[9px] text-caption">
              <span className="inline-flex h-5 w-5 items-center justify-center rounded-control" style={{ background: meta.color + "20", color: meta.color }}>
                <Icon name={meta.iconName} size={12} />
              </span>
              <span className="font-semibold text-fg-2">{f.name}</span>
              <span className="font-mono text-mini text-muted">
                {meta.label}
                {/* size=0 表示未知（能力包旧存档只有元信息），不显示误导性的 0 B */}
                {f.size > 0 ? ` · ${formatFileSize(f.size)}` : ""}
                {f.pages ? ` · ${f.pages}p` : ""}
              </span>
            </span>
          );
        })}
      </div>
    </div>
  );
}

export function DropOverlay({ visible }: { visible: boolean }) {
  const { t } = useT();
  // ファイルを持ち込むと画面全体で受け止め、離すと消える（出入りとも動かす）
  return (
    <AnimatePresence>
      {visible && (
    <m.div
      key="drop"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: DURATION.exit, ease: EASE.in } }}
      className="pointer-events-none fixed inset-0 z-[300] grid place-items-center bg-[rgba(20,18,15,0.55)] backdrop-blur-[4px]"
    >
      <m.div
        initial={{ scale: 0.94, y: 8 }}
        animate={{ scale: 1, y: 0 }}
        className="w-[420px] max-w-[80vw] rounded-[18px] border-2 border-dashed border-accent bg-surface p-10 text-center text-fg shadow-e3 max-md:w-[calc(100vw-48px)] max-md:p-7">
        <svg viewBox="0 0 48 48" width="40" height="40" className="mx-auto mb-3 text-accent">
          <path d="M14 28V14a4 4 0 014-4h11l9 9v17a4 4 0 01-4 4H14" stroke="currentColor" strokeWidth="2" fill="none" strokeLinejoin="round" />
          <path d="M29 10v9h9" stroke="currentColor" strokeWidth="2" fill="none" strokeLinejoin="round" />
          <path d="M10 32v9M5 36.5l5-5 5 5" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <div className="mb-1.5 text-title font-bold">{t.uploads.dropTitle}</div>
        <div className="text-footnote leading-[1.5] text-muted">{t.uploads.dropSubtitle}</div>
      </m.div>
    </m.div>
      )}
    </AnimatePresence>
  );
}

/** relPath の先頭ディレクトリでグルーピングする（フラット展開だが UI 上は出自を保つ）。 */
function groupByFolder(files: StagedFile[]): { folder: string | null; files: StagedFile[] }[] {
  const groups = new Map<string, StagedFile[]>();
  for (const f of files) {
    const top = f.relPath?.includes("/") ? f.relPath.split("/")[0] : "";
    const arr = groups.get(top) ?? [];
    arr.push(f);
    groups.set(top, arr);
  }
  return [...groups.entries()].map(([folder, fs]) => ({ folder: folder || null, files: fs }));
}

function QueueGroup({ folder, files, onRemove, onRetry }: {
  folder: string | null; files: StagedFile[]; onRemove: (id: string) => void; onRetry?: (id: string) => void;
}) {
  const { t } = useT();
  const [open, setOpen] = useState(true);
  const done = files.filter((f) => f.status === "ready").length;
  const failed = files.filter((f) => f.status === "error").length;
  const skipped = files.filter((f) => f.status === "skipped").length;
  // スキップは完了の分母から除外する（取り込み対象のみを母数に）。
  const target = files.length - skipped;
  const active = target - done - failed;

  // フォルダ無し（個別ファイル）はヘッダーを出さずにそのまま並べる。
  if (!folder) {
    return (
      <div className="flex flex-col gap-1.5">
        {files.map((f) => <AttachmentChip key={f.id} file={f} onRemove={onRemove} onRetry={onRetry} />)}
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-card border-[0.5px] border-divider-strong bg-bg-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-2.5 py-2 text-left hover:bg-divider"
      >
        <Icon name="folder" size={13} />
        <span className="min-w-0 flex-1 truncate text-footnote font-semibold text-fg" title={folder}>{folder}</span>
        <span className="shrink-0 font-mono text-mini text-muted">
          {interpolate(t.uploads.groupDone, { done, target })}
          {failed ? ` · ${interpolate(t.uploads.groupFailed, { n: failed })}` : ""}
          {skipped ? ` · ${interpolate(t.uploads.groupSkipped, { n: skipped })}` : ""}
        </span>
        {active > 0 && <span className="h-[10px] w-[10px] shrink-0 animate-spin-fast rounded-full border-[1.5px] border-divider-strong border-t-accent" />}
        <svg viewBox="0 0 12 12" width="10" height="10" className={cn("shrink-0 text-muted transition-transform", open && "rotate-90")}>
          <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div className="flex flex-col gap-1.5 px-1.5 pb-1.5">
          {files.map((f) => <AttachmentChip key={f.id} file={f} onRemove={onRemove} onRetry={onRetry} />)}
        </div>
      )}
    </div>
  );
}

/** 文書管理モーダル内のアップロードキュー。フォルダ単位にまとめ、段階進捗を表示する。 */
export function DocumentsUploadQueue({ files, onRemove, onRetry, onClear }: {
  files: StagedFile[]; onRemove: (id: string) => void; onRetry?: (id: string) => void; onClear?: () => void;
}) {
  const { t } = useT();
  if (!files.length) return null;
  const groups = groupByFolder(files);
  const skipped = files.filter((f) => f.status === "skipped").length;
  const target = files.length - skipped; // スキップを除いた取り込み対象数。
  const done = files.filter((f) => f.status === "ready").length;
  const allDone = done + skipped === files.length;

  return (
    <div className="flex min-h-0 max-h-[50vh] flex-col border-b-[0.5px] border-divider bg-surface-2 max-md:max-h-[55vh]">
      <div className="flex items-center gap-2 px-3 py-2">
        <span className="text-caption font-semibold uppercase tracking-[0.05em] text-muted">{t.uploads.queueHeader}</span>
        <span className="font-mono text-mini text-muted">
          {interpolate(t.uploads.queueProgress, { done, target })}
          {skipped ? ` · ${interpolate(t.uploads.queueSkipped, { n: skipped })}` : ""}
        </span>
        {onClear && (
          <button
            onClick={onClear}
            className="ml-auto rounded-control border-0 bg-transparent px-1.5 py-0.5 text-mini font-medium text-muted hover:bg-divider hover:text-fg"
          >
            {allDone ? t.uploads.clearAll : t.uploads.hideAll}
          </button>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2.5">
        <div className="flex flex-col gap-1.5">
          {groups.map((g) => (
            <QueueGroup key={g.folder ?? "__loose__"} folder={g.folder} files={g.files} onRemove={onRemove} onRetry={onRetry} />
          ))}
        </div>
      </div>
    </div>
  );
}

