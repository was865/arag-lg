"use client";

// 原本プレビュー（P3 の簡易版）。PDF と画像はブラウザで表示し、それ以外はダウンロード導線を出す。
// 旧版の表計算・Office→PDF 変換・テキスト表示は文書画面（P4）で移植する。
import type { Dictionary } from "@/i18n/dictionary";
import { useT } from "@/i18n/context";
import { isImage, isPdf } from "@/lib/file-types";

const PDF_VIEW_PARAMS = "toolbar=0&navpanes=0&statusbar=0&view=FitH";

export function originalUrl(docId: string): string {
  return `/api/v1/documents/${encodeURIComponent(docId)}/original`;
}

export function originalTabLabel(_filename: string, t: Dictionary): string {
  return t.documents.tabOriginal;
}

export function UnsupportedPreview({ docId, onShowParsed }: { docId: string; onShowParsed?: () => void }) {
  const { t } = useT();
  return (
    <div className="grid h-full place-items-center p-8 text-center">
      <div className="max-w-[380px]">
        <div className="mb-1.5 text-[13px] font-semibold text-fg">{t.documents.unsupportedTitle}</div>
        <div className="mb-4 text-[12px] leading-[1.6] text-muted">{t.documents.unsupportedDescription}</div>
        <div className="flex items-center justify-center gap-2">
          <a
            href={originalUrl(docId)}
            download
            className="inline-flex items-center gap-1.5 rounded-lg border-[0.5px] border-divider-strong bg-surface px-3 py-1.5 text-[12px] font-medium text-fg hover:bg-surface-2"
          >{t.documents.unsupportedDownload}</a>
          {onShowParsed && (
            <button
              onClick={onShowParsed}
              className="inline-flex items-center rounded-lg border-[0.5px] border-divider-strong bg-surface px-3 py-1.5 text-[12px] font-medium text-fg hover:bg-surface-2"
            >{t.sources.showCitedText}</button>
          )}
        </div>
      </div>
    </div>
  );
}

interface OriginalPreviewProps {
  docId: string;
  filename: string;
  pdfPage?: number;
  onShowParsed?: () => void;
}

export function OriginalPreview({ docId, filename, pdfPage, onShowParsed }: OriginalPreviewProps) {
  const url = originalUrl(docId);
  if (isPdf(filename)) {
    const src = `${url}#${pdfPage ? `page=${pdfPage}&` : ""}${PDF_VIEW_PARAMS}`;
    return <iframe key={pdfPage ?? 0} title={filename} src={src} className="h-full w-full border-0" />;
  }
  if (isImage(filename)) {
    return (
      <div className="grid h-full place-items-center p-5">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={url} alt={filename} className="max-h-full max-w-full rounded-lg border-[0.5px] border-divider" />
      </div>
    );
  }
  return <UnsupportedPreview docId={docId} onShowParsed={onShowParsed} />;
}
