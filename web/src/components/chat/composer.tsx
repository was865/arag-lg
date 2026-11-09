"use client";

import { SHORTCUT_LABEL } from "@/lib/shortcuts";
import { useEffect, useRef, useState } from "react";
import { Icon } from "@/components/icons";
import { ModelPicker } from "@/components/chat/model-picker";
import { ScopePicker } from "@/components/chat/scope-picker";
import { AttachmentTray } from "@/components/uploads/uploads";
import { ACCEPTED_FILE_TYPES } from "@/lib/constants";
import { cn } from "@/lib/utils";
import type { ModelOption, ScopeValue, StagedFile } from "@/lib/types";
import { imageFromClipboard, QUERY_IMAGE_ACCEPT, type QueryImage } from "@/lib/query-image";
import { useT } from "@/i18n/context";

/** 快捷条件チップ挿入: 末尾に snippet を追記する。空入力ならそのまま、既に区切り(，/、/,/空白)で
 *  終わっていなければ全角読点で連結する。追問「追加条件继续」の導線で用いる。 */
export function appendSnippet(value: string, snippet: string): string {
  const base = value.replace(/\s+$/, "");
  if (!base) return snippet;
  const sep = /[，、,\s]$/.test(base) ? "" : "，";
  return base + sep + snippet;
}

/** 送信可否判定。添付が1件でも処理中(pending)なら送信不可。空入力かつ ready 添付・画像なしも不可。 */
export function composerSubmitState(
  { value, attachments, running, hasImage = false }: { value: string; attachments: StagedFile[]; running: boolean; hasImage?: boolean },
): { pending: boolean; canSubmit: boolean } {
  const pending = attachments.some((a) => a.status === "uploading" || a.status === "processing");
  const hasReady = attachments.some((a) => a.status === "ready");
  const canSubmit = !running && !pending && (value.trim() !== "" || hasReady || hasImage);
  return { pending, canSubmit };
}

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  model: ModelOption;
  /** 外部のモデル変更経路（chat は設定モーダル）。models 指定時は不要。 */
  onChangeModel?: () => void;
  /** 指定するとモデルボタンが内蔵 ModelPicker ポップオーバーを開く（agents 経路）。 */
  models?: ModelOption[];
  /** 内蔵 ModelPicker での選択コールバック（models とセットで指定）。 */
  onSelectModel?: (m: ModelOption) => void;
  running: boolean;
  /** 添付一式は任意。onAttachFiles 未指定なら添付ボタン・トレイごと非表示（agents 経路）。 */
  attachments?: StagedFile[];
  onAttachFiles?: (files: FileList | null) => void;
  onRemoveAttachment?: (id: string) => void;
  onRetryAttachment?: (id: string) => void;
  /** file input の accept 上書き（agents 経路の能力包附件用）。未指定は chat 既定の文書型。 */
  attachAccept?: string;
  /** 検索範囲は任意。未指定ならスコープボタン非表示（agents 経路）。 */
  scope?: ScopeValue;
  onChangeScope?: (s: ScopeValue) => void;
  /** プレースホルダの上書き（running 状態も呼び出し側で織り込んで渡す）。 */
  placeholder?: string;
  /** agents 経路の書式ヒント（識別码アイコン + 文言）。空白态で「何を入力するか」を提示。 */
  leadingHint?: string;
  /** agents 経路の追加条件チップ。点选で snippet を末尾に追記しフォーカス。 */
  quickInserts?: { label: string; snippet: string }[];
  /** agents 経路の「最近」候補（新しい順）。空なら「最近」ボタン非表示。 */
  recentQueries?: string[];
  /** 「最近」候補の選択（入力欄へ投入）。recentQueries とセットで指定。 */
  onPickRecent?: (query: string) => void;
  /** 変わるたびに入力欄へフォーカスする（ライブラリから「質問」で戻ったときなど）。0 は何もしない。 */
  focusKey?: number;
  /** 質問に添える画像（specs/017）。onPickImage 未指定なら画像ボタン・貼り付け・ドロップは無効。 */
  image?: QueryImage | null;
  /** 縮小などの処理中（送信不可） */
  imageBusy?: boolean;
  onPickImage?: (f: File) => void;
  onRemoveImage?: () => void;
}

export function Composer({
  value,
  onChange,
  onSubmit,
  onStop,
  model,
  onChangeModel,
  models,
  onSelectModel,
  running,
  attachments = [],
  onAttachFiles,
  onRemoveAttachment,
  onRetryAttachment,
  attachAccept,
  scope,
  onChangeScope,
  placeholder,
  leadingHint,
  quickInserts,
  recentQueries = [],
  onPickRecent,
  focusKey = 0,
  image = null,
  imageBusy = false,
  onPickImage,
  onRemoveImage,
}: Props) {
  const taRef = useRef<HTMLTextAreaElement>(null);
  const imageRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const scopeRef = useRef<HTMLButtonElement>(null);
  const modelRef = useRef<HTMLButtonElement>(null);
  const recentRef = useRef<HTMLButtonElement>(null);
  const [scopeOpen, setScopeOpen] = useState(false);
  const [modelOpen, setModelOpen] = useState(false);
  const [recentOpen, setRecentOpen] = useState(false);
  const { t } = useT();
  // 内蔵 ModelPicker を使うか（agents）／外部経路に委ねるか（chat=設定モーダル）
  const hasInlineModelPicker = Boolean(models && onSelectModel);

  // 内容に合わせて高さを変える。幅が変わると折り返しも変わるので、幅の変化でも測り直す
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    const fit = () => {
      ta.style.height = "auto";
      ta.style.height = Math.min(180, ta.scrollHeight) + "px";
    };
    fit();
    let width = ta.clientWidth;
    const ro = new ResizeObserver(() => {
      if (ta.clientWidth !== width) {
        width = ta.clientWidth;
        fit();
      }
    });
    ro.observe(ta);
    return () => ro.disconnect();
  }, [value]);

  useEffect(() => {
    if (focusKey) taRef.current?.focus();
  }, [focusKey]);

  const submitState = composerSubmitState({ value, attachments, running, hasImage: Boolean(image) });
  const pending = submitState.pending || imageBusy;
  const canSubmit = submitState.canSubmit && !imageBusy;
  const toolBtn = "inline-flex h-7 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-[7px] border-0 bg-transparent px-2 text-[12px] font-medium text-muted hover:bg-divider hover:text-fg max-md:h-8";

  // 追加条件チップ: 末尾に snippet を追記し、カーソルを末尾へ置いてフォーカス。
  const insertSnippet = (snippet: string) => {
    const next = appendSnippet(value, snippet);
    onChange(next);
    requestAnimationFrame(() => {
      const ta = taRef.current;
      if (!ta) return;
      ta.focus();
      ta.setSelectionRange(next.length, next.length);
    });
  };

  const showQuickInserts = Boolean(quickInserts?.length) && !running;
  const showRecent = recentQueries.length > 0 && Boolean(onPickRecent) && !running;
  const showLeadingHint = Boolean(leadingHint) && !showQuickInserts && !running;

  return (
    <form
      className="mx-auto w-full max-w-[1020px] px-8 pb-[18px] pt-3.5 max-md:min-w-0 max-md:px-3 max-md:pb-[max(12px,env(safe-area-inset-bottom))] max-md:pt-2.5"
      onSubmit={(e) => {
        e.preventDefault();
        if (!running && canSubmit) onSubmit();
      }}
      onDragOver={(e) => {
        if (!onPickImage || running || !Array.from(e.dataTransfer.types).includes("Files")) return;
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        setDragging(false);
        const f = onPickImage && !running ? imageFromClipboard(e.dataTransfer) : null;
        if (!f) return;
        e.preventDefault();
        onPickImage!(f);
      }}
    >
      <div
        data-tour="composer"
        className={cn(
          "rounded-[16px] border border-divider-strong bg-surface shadow-e2 transition-[border-color,box-shadow] focus-within:border-accent focus-within:shadow-[0_0_0_3px_var(--accent-soft),var(--shadow-2)] max-md:rounded-[14px]",
        )}
      >
        {onRemoveAttachment && (
          <AttachmentTray files={attachments} onRemove={onRemoveAttachment} onRetry={onRetryAttachment} />
        )}
        {(image || imageBusy) && (
          <div className="flex items-center gap-2 px-3 pt-3">
            <div className="relative h-14 w-14 shrink-0 overflow-hidden rounded-[10px] border-[0.5px] border-divider-strong bg-surface-2">
              {image ? (
                // eslint-disable-next-line @next/next/no-img-element -- data URL の縮小表示
                <img src={image.dataUrl} alt={t.chat.imageAttached} className="h-full w-full object-cover" />
              ) : (
                <span className="absolute inset-0 m-auto h-4 w-4 animate-spin-fast rounded-full border-[1.5px] border-divider-strong border-t-accent" />
              )}
              {image && onRemoveImage && !running && (
                <button
                  type="button"
                  onClick={onRemoveImage}
                  aria-label={t.chat.imageRemove}
                  title={t.chat.imageRemove}
                  className="absolute right-0.5 top-0.5 inline-flex h-5 w-5 items-center justify-center rounded-full bg-[rgba(20,18,15,0.6)] text-white hover:bg-[rgba(20,18,15,0.8)]"
                >
                  <svg viewBox="0 0 16 16" width="10" height="10" aria-hidden>
                    <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                  </svg>
                </button>
              )}
            </div>
            <span className="min-w-0 text-[11.5px] leading-[1.45] text-muted">{imageBusy ? t.chat.imagePreparing : t.chat.imageHint}</span>
          </div>
        )}
        {dragging && (
          <div className="px-4 pt-3 text-[12px] font-medium text-accent">{t.chat.imageDrop}</div>
        )}
        {onPickImage && (
          <input
            ref={imageRef}
            type="file"
            accept={QUERY_IMAGE_ACCEPT}
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onPickImage(f);
              e.target.value = "";
            }}
          />
        )}
        {onAttachFiles && (
          <input
            ref={fileRef}
            type="file"
            accept={attachAccept ?? ACCEPTED_FILE_TYPES}
            multiple
            className="hidden"
            onChange={(e) => {
              onAttachFiles(e.target.files);
              e.target.value = "";
            }}
          />
        )}
        <textarea
          ref={taRef}
          rows={1}
          value={value}
          disabled={running}
          onChange={(e) => onChange(e.target.value)}
          onPaste={(e) => {
            const f = onPickImage && !running ? imageFromClipboard(e.clipboardData) : null;
            if (!f) return;
            e.preventDefault();
            onPickImage!(f);
          }}
          placeholder={placeholder ?? (running ? t.chat.placeholderRunning : t.chat.placeholderIdle)}
          onKeyDown={(e) => {
            // IME 変換確定の Enter（isComposing / keyCode 229）は送信しない
            if (e.nativeEvent.isComposing || e.keyCode === 229) return;
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (canSubmit) onSubmit();
            }
          }}
          className={cn(
            "max-h-[180px] min-h-[24px] w-full resize-none border-0 bg-transparent px-4 pb-1 pt-3.5 text-[14.5px] leading-[1.5] text-fg outline-none placeholder:text-muted-2 max-md:px-3.5 max-md:text-[16px]",
            running && "text-muted",
          )}
        />
        <div className="flex items-center gap-1 px-2 pb-2 pt-1 max-md:gap-0.5 max-md:px-1.5">
          {onAttachFiles && (
            <button type="button" className={toolBtn} title={t.chat.attachTitle} disabled={running} onClick={() => fileRef.current?.click()}>
              <Icon name="paperclip" size={13} />
            </button>
          )}
          {onPickImage && (
            <button
              type="button"
              className={toolBtn}
              title={t.chat.imageAttachTitle}
              aria-label={t.chat.imageAttachTitle}
              disabled={running}
              onClick={() => imageRef.current?.click()}
            >
              <Icon name="image" size={14} />
            </button>
          )}
          {scope && onChangeScope && (
            <>
              <button
                ref={scopeRef}
                type="button"
                data-tour="scope"
                className={cn(toolBtn, scopeOpen && "bg-divider text-fg")}
                title={t.chat.scopeTitle}
                disabled={running}
                onClick={() => setScopeOpen((o) => !o)}
              >
                <span className="inline-flex items-center">
                  <Icon name={scope.iconName} size={13} />
                </span>
                <span className="max-md:max-w-[80px] max-md:truncate">{scope.label}</span>
                <svg viewBox="0 0 16 16" width="9" height="9">
                  <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
              <ScopePicker
                open={scopeOpen}
                anchorRef={scopeRef}
                value={scope}
                onChange={onChangeScope}
                onClose={() => setScopeOpen(false)}
                attachmentCount={attachments.filter((a) => a.status === "ready").length}
              />
            </>
          )}
          {/* 书式ヒント（空白态・agents）: 識別码アイコン + 対応する入力種別。 */}
          {showLeadingHint && (
            <span className="inline-flex h-7 min-w-0 shrink items-center gap-1.5 rounded-[7px] px-2 text-[12px] font-medium text-muted-2 max-md:hidden">
              <Icon name="hash" size={13} />
              <span className="truncate">{leadingHint}</span>
            </span>
          )}
          {/* 追加条件チップ（対話中・agents）: 点选で snippet を末尾に追記。 */}
          {showQuickInserts &&
            quickInserts!.map((qi) => (
              <button
                key={qi.label}
                type="button"
                className={toolBtn}
                title={qi.label}
                disabled={running}
                onClick={() => insertSnippet(qi.snippet)}
              >
                {qi.label}
              </button>
            ))}
          {/* 最近（agents）: 直近クエリのポップオーバー。行を増やさず高さ固定。 */}
          {showRecent && (
            <>
              <button
                ref={recentRef}
                type="button"
                className={cn(toolBtn, recentOpen && "bg-divider text-fg")}
                title="最近的查询"
                disabled={running}
                onClick={() => setRecentOpen((o) => !o)}
              >
                <Icon name="clock" size={13} />
                <span className="max-md:hidden">最近</span>
              </button>
              <RecentPopover
                open={recentOpen}
                anchorRef={recentRef}
                queries={recentQueries}
                onPick={(q) => {
                  onPickRecent!(q);
                  setRecentOpen(false);
                  taRef.current?.focus();
                }}
                onClose={() => setRecentOpen(false)}
              />
            </>
          )}
          <div className="min-w-0 flex-1" />
          <button
            ref={modelRef}
            type="button"
            onClick={hasInlineModelPicker ? () => setModelOpen((o) => !o) : onChangeModel}
            disabled={running}
            className={cn(
              "inline-flex h-7 shrink items-center gap-1.5 whitespace-nowrap rounded-[7px] border-0 bg-transparent px-2.5 text-[12px] font-medium text-fg-2 hover:bg-divider hover:text-fg max-md:max-w-[36vw] max-md:overflow-hidden max-md:text-ellipsis max-md:px-2 max-md:text-[11.5px]",
              modelOpen && "bg-divider text-fg",
            )}
          >
            <span className="h-1.5 w-1.5 rounded-full bg-accent" />
            {model.label}
            <svg viewBox="0 0 16 16" width="10" height="10">
              <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          {hasInlineModelPicker && (
            <ModelPicker
              open={modelOpen}
              anchorRef={modelRef}
              models={models!}
              value={model.id}
              onChange={(m) => onSelectModel!(m)}
              onClose={() => setModelOpen(false)}
            />
          )}
          {running ? (
            <button
              type="button"
              onClick={onStop}
              title={t.chat.stopTitle}
              className="grid h-8 w-8 shrink-0 animate-[ar-hl-pulse_1.6s_ease-in-out_infinite] place-items-center rounded-lg border-0 bg-accent text-white max-md:h-[34px] max-md:w-[34px]"
            >
              <svg viewBox="0 0 16 16" width="10" height="10">
                <rect x="3" y="3" width="10" height="10" rx="1.5" fill="currentColor" />
              </svg>
            </button>
          ) : (
            <button
              type="submit"
              disabled={!canSubmit}
              title={pending ? t.chat.pendingSubmitTitle : undefined}
              className={cn(
                "grid h-8 w-8 shrink-0 place-items-center rounded-lg border-0 text-white transition-[background,filter] max-md:h-[34px] max-md:w-[34px]",
                canSubmit ? "bg-accent hover:brightness-105" : "cursor-not-allowed bg-divider text-muted-2",
              )}
            >
              <svg viewBox="0 0 16 16" width="13" height="13">
                <path d="M8 13V3M8 3l-4 4M8 3l4 4" stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          )}
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-x-1.5 gap-y-1 pt-2 text-center text-[11px] text-muted-2 max-md:hidden">
        {running ? (
          <span><kbd>{SHORTCUT_LABEL.stop}</kbd>{t.chat.cancelHintText}</span>
        ) : pending ? (
          t.chat.pendingHint
        ) : (
          <>
            <span><kbd>Enter</kbd>{t.chat.hintSend}</span>
            <span className="text-divider-strong">·</span>
            <span><kbd>Shift+Enter</kbd>{t.chat.hintNewline}</span>
            {/* ファイルドロップは添付経路があるときだけ案内する */}
            {onAttachFiles && (
              <>
                <span className="text-divider-strong">·</span>
                <span>{t.chat.hintDrop}</span>
              </>
            )}
            <span className="text-divider-strong">·</span>
            <span><kbd>{SHORTCUT_LABEL.newThread}</kbd>{t.chat.hintNewThread}</span>
          </>
        )}
      </div>
    </form>
  );
}

/** 「最近」ポップオーバー: 直近クエリを一覧し、点选で入力欄へ投入する。
 *  ModelPicker と同系の錨定/外側クリック閉じ（右揃え・上向き）を踏襲する。 */
function RecentPopover({
  open,
  anchorRef,
  queries,
  onPick,
  onClose,
}: {
  open: boolean;
  anchorRef: React.RefObject<HTMLButtonElement | null>;
  queries: string[];
  onPick: (query: string) => void;
  onClose: () => void;
}) {
  const [pos, setPos] = useState({ left: 0, bottom: 0 });

  useEffect(() => {
    if (!open || !anchorRef.current) return;
    const r = anchorRef.current.getBoundingClientRect();
    setPos({ left: Math.max(8, r.left), bottom: window.innerHeight - r.top + 6 });
  }, [open, anchorRef]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    const onDown = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest(".recent-pop") && !anchorRef.current?.contains(target)) onClose();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onDown);
    };
  }, [open, onClose, anchorRef]);

  if (!open) return null;

  return (
    <div
      className="recent-pop fixed z-[150] flex max-h-[320px] w-[320px] animate-pop-in flex-col overflow-hidden rounded-[14px] border-[0.5px] border-divider-strong bg-surface shadow-e3 max-md:w-[min(320px,calc(100vw-20px))]"
      style={{ left: pos.left, bottom: pos.bottom }}
    >
      <div className="border-b-[0.5px] border-divider px-3.5 py-2.5 text-[12px] font-semibold text-muted">
        最近的查询
      </div>
      <div className="overflow-y-auto p-1.5">
        {queries.map((q, i) => (
          <button
            key={`${i}-${q}`}
            type="button"
            onClick={() => onPick(q)}
            title={q}
            className="flex w-full items-center gap-2 rounded-lg border-0 bg-transparent px-2.5 py-2 text-left hover:bg-divider"
          >
            <Icon name="clock" size={13} className="shrink-0 text-muted-2" />
            <span className="min-w-0 flex-1 truncate text-[13px] text-fg">{q}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
