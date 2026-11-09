"use client";

/** スレッドの共有ダイアログ（specs/008-thread-share R7）。公開範囲を選び、リンクをコピーする。 */
import { useEffect, useState } from "react";
import { Icon } from "@/components/icons";
import { useToast } from "@/components/feedback/toast-provider";
import { ApiError, chatApi, type ThreadOut } from "@/lib/chat/api";
import { shareUrl, VISIBILITY_OPTIONS, type Visibility } from "@/lib/share";
import { cn } from "@/lib/utils";

export interface ShareDialogProps {
  thread: ThreadOut;
  onChange: (thread: ThreadOut) => void;
  onClose: () => void;
}

export function ShareDialog({ thread, onChange, onClose }: ShareDialogProps) {
  const push = useToast();
  const [visibility, setVisibility] = useState<Visibility>(thread.visibility ?? "private");
  const [token, setToken] = useState<string | null>(thread.share_token ?? null);
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const link = shareUrl(window.location.origin, visibility, token);

  const pick = async (next: Visibility) => {
    if (next === visibility || saving) return;
    const prev = visibility;
    setVisibility(next);
    setSaving(true);
    try {
      const t = await chatApi.patchThread(thread.id, { visibility: next });
      setToken(t.share_token ?? null);
      onChange(t);
    } catch (e) {
      setVisibility(prev); // 失敗したらサーバの状態に戻す
      push(e instanceof ApiError ? e.message : "公開範囲を変えられませんでした", "error");
    } finally {
      setSaving(false);
    }
  };

  const copy = async () => {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      push("コピーできませんでした。リンクを選んでコピーしてください", "error");
    }
  };

  return (
    <div
      className="fixed inset-0 z-[240] grid animate-overlay-in place-items-center bg-[rgba(20,18,15,0.35)] p-6 max-md:items-end max-md:p-0"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="スレッドを共有"
        onClick={(e) => e.stopPropagation()}
        className="flex w-[460px] max-w-full animate-pop-in flex-col gap-4 rounded-[16px] border-[0.5px] border-divider-strong bg-surface p-[20px_20px_16px] shadow-e3 max-md:w-full max-md:rounded-[18px_18px_0_0] max-md:pb-[max(16px,env(safe-area-inset-bottom))]"
      >
        <div className="flex items-center gap-2">
          <h3 className="m-0 min-w-0 flex-1 truncate text-[15px] font-bold text-fg">スレッドを共有</h3>
          <button
            onClick={onClose}
            aria-label="閉じる"
            className="grid h-7 w-7 place-items-center rounded-md text-muted hover:bg-divider hover:text-fg"
          >
            <Icon name="close" size={13} />
          </button>
        </div>

        <div role="radiogroup" aria-label="公開範囲" className="flex flex-col gap-1">
          {VISIBILITY_OPTIONS.map((o) => {
            const on = o.id === visibility;
            return (
              <button
                key={o.id}
                role="radio"
                aria-checked={on}
                disabled={saving}
                onClick={() => void pick(o.id)}
                className={cn(
                  "flex items-center gap-3 rounded-[10px] border-[0.5px] px-3 py-2.5 text-left disabled:cursor-wait",
                  on ? "border-accent bg-accent-soft" : "border-divider hover:bg-surface-2",
                )}
              >
                <span
                  className={cn(
                    "grid h-8 w-8 shrink-0 place-items-center rounded-lg",
                    on ? "bg-accent text-white" : "bg-surface-2 text-muted",
                  )}
                >
                  <Icon name={o.iconName} size={14} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[13px] font-semibold text-fg">{o.label}</span>
                  <span className="block text-[11.5px] text-muted">{o.desc}</span>
                </span>
                {on && <Icon name="check" size={14} />}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-2 rounded-[10px] border-[0.5px] border-divider-strong bg-surface-2 py-1 pl-3 pr-1">
          <Icon name="link" size={13} />
          <input
            readOnly
            value={link ?? ""}
            placeholder={visibility === "private" ? "自分のみの会話にはリンクを出しません" : "リンクを作っています…"}
            onFocus={(e) => e.currentTarget.select()}
            aria-label="共有リンク"
            className="min-w-0 flex-1 border-0 bg-transparent font-mono text-[12px] text-fg-2 outline-none placeholder:font-sans placeholder:text-muted-2"
          />
          <button
            onClick={() => void copy()}
            disabled={!link}
            className={cn(
              "h-[30px] shrink-0 whitespace-nowrap rounded-[7px] px-3.5 text-[12px] font-semibold disabled:cursor-not-allowed disabled:opacity-50",
              copied ? "bg-accent text-white" : "bg-fg text-bg",
            )}
          >
            {copied ? "コピーしました" : "コピー"}
          </button>
        </div>
        {visibility === "public" && (
          <p className="m-0 text-[11.5px] leading-[1.6] text-muted">
            回答と出典の文書名が、リンクを知っている人に見えます。文書の本文は見えません。
          </p>
        )}
      </div>
    </div>
  );
}
