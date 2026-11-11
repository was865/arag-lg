"use client";

/** スレッドの共有ダイアログ（specs/008-thread-share R7）。公開範囲を選び、リンクをコピーする。 */
import { useState } from "react";
import { Icon } from "@/components/icons";
import { Button, ICON } from "@/components/ui/button";
import { ChoiceList } from "@/components/ui/choice";
import { Dialog, DialogBody, DialogContent } from "@/components/ui/dialog";
import { useToast } from "@/components/feedback/toast-provider";
import { ApiError, chatApi, type ThreadOut } from "@/lib/chat/api";
import { shareUrl, VISIBILITY_OPTIONS, type Visibility } from "@/lib/share";

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
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="スレッドを共有" size="sm">
        <DialogBody className="flex flex-col gap-4">
          <ChoiceList
            label="公開範囲"
            value={visibility}
            disabled={saving}
            options={VISIBILITY_OPTIONS.map((o) => ({ id: o.id, label: o.label, hint: o.desc, icon: o.iconName }))}
            onChange={(v) => void pick(v)}
          />
          <div className="flex items-center gap-2 rounded-control border-[0.5px] border-divider-strong bg-surface py-1 pl-3 pr-1">
            <Icon name="link" size={ICON.sm} className="shrink-0 text-muted" />
            <input
              readOnly
              value={link ?? ""}
              placeholder={visibility === "private" ? "自分のみの会話にはリンクを出しません" : "リンクを作っています…"}
              onFocus={(e) => e.currentTarget.select()}
              aria-label="共有リンク"
              className="min-w-0 flex-1 border-0 bg-transparent font-mono text-footnote text-fg-2 outline-none placeholder:font-sans placeholder:text-muted-2"
            />
            <Button variant={copied ? "secondary" : "primary"} size="sm" onClick={() => void copy()} disabled={!link}>
              {copied && <Icon name="check" size={ICON.sm} />}
              {copied ? "コピーしました" : "コピー"}
            </Button>
          </div>
          {visibility === "public" && (
            <p className="m-0 text-caption text-muted">
              回答と出典の文書名が、リンクを知っている人に見えます。文書の本文は見えません。
            </p>
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
