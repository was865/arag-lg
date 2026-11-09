"use client";

/** アカウント（specs/006-auth R11）: 表示名・パスワードの変更・ログイン中の端末。 */
import { useCallback, useEffect, useState } from "react";
import { FIELD, Notice, Spinner } from "@/components/auth/auth-card";
import { Icon } from "@/components/icons";
import { useToast } from "@/components/feedback/toast-provider";
import { authClient, authErrorMessage } from "@/lib/auth/client";
import { describeAgent } from "@/lib/auth/user";
import { relativeTime } from "@/lib/utils";

interface SessionRow {
  id: string;
  token: string;
  userAgent?: string | null;
  ipAddress?: string | null;
  updatedAt: Date | string;
}

const BTN =
  "inline-flex h-8 shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg border-0 bg-accent px-3 text-[12.5px] font-semibold text-white hover:brightness-105 disabled:opacity-60";
const BTN_GHOST =
  "inline-flex h-8 shrink-0 items-center justify-center whitespace-nowrap rounded-lg border-[0.5px] border-divider-strong bg-surface px-3 text-[12.5px] font-medium text-fg hover:bg-surface-2 disabled:opacity-60";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3 border-b-[0.5px] border-divider px-5 py-4 last:border-b-0">
      <h3 className="m-0 text-[13px] font-semibold text-fg">{title}</h3>
      {children}
    </section>
  );
}

export function AccountModal({ onClose }: { onClose: () => void }) {
  const push = useToast();
  const { data, refetch } = authClient.useSession();
  const user = data?.user;
  const currentToken = data?.session.token;

  const [name, setName] = useState(user?.name ?? "");
  const [savingName, setSavingName] = useState(false);

  const [pw, setPw] = useState({ current: "", next: "", confirm: "", revoke: true });
  const [pwBusy, setPwBusy] = useState(false);
  const [pwError, setPwError] = useState("");

  const [sessions, setSessions] = useState<SessionRow[] | null>(null);

  const loadSessions = useCallback(async () => {
    const { data } = await authClient.listSessions();
    setSessions((data ?? []) as SessionRow[]);
  }, []);

  useEffect(() => {
    authClient.listSessions().then(({ data }) => setSessions((data ?? []) as SessionRow[]));
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const saveName = async () => {
    const v = name.trim();
    if (!v || v === user?.name) return;
    setSavingName(true);
    const { error } = await authClient.updateUser({ name: v });
    setSavingName(false);
    if (error) return push(authErrorMessage(error), "error");
    await refetch();
    push("表示名を変更しました", "success");
  };

  const changePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPwError("");
    if (pw.next !== pw.confirm) return setPwError("確認用のパスワードが一致しません");
    setPwBusy(true);
    const { error } = await authClient.changePassword({
      currentPassword: pw.current,
      newPassword: pw.next,
      revokeOtherSessions: pw.revoke,
    });
    setPwBusy(false);
    if (error) {
      return setPwError(
        error.code === "INVALID_PASSWORD" ? "現在のパスワードが正しくありません" : authErrorMessage(error),
      );
    }
    setPw({ current: "", next: "", confirm: "", revoke: pw.revoke });
    push("パスワードを変更しました", "success");
    void loadSessions();
  };

  const revoke = async (token: string) => {
    const { error } = await authClient.revokeSession({ token });
    if (error) return push(authErrorMessage(error), "error");
    void loadSessions();
  };

  const revokeOthers = async () => {
    const { error } = await authClient.revokeOtherSessions();
    if (error) return push(authErrorMessage(error), "error");
    push("ほかの端末からログアウトしました", "success");
    void loadSessions();
  };

  const others = sessions?.filter((s) => s.token !== currentToken).length ?? 0;

  return (
    <div
      className="fixed inset-0 z-[230] grid animate-overlay-in place-items-center bg-[rgba(20,18,15,0.35)] p-6 max-md:items-end max-md:p-0"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="アカウント"
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[86vh] w-[520px] max-w-full animate-pop-in flex-col overflow-hidden rounded-[16px] border-[0.5px] border-divider-strong bg-surface shadow-e3 max-md:w-full max-md:rounded-[18px_18px_0_0]"
      >
        <header className="flex items-center gap-2 border-b-[0.5px] border-divider px-5 py-3.5">
          <h2 className="m-0 flex-1 text-[15px] font-bold text-fg">アカウント</h2>
          <button
            onClick={onClose}
            aria-label="閉じる"
            className="grid h-7 w-7 place-items-center rounded-md text-muted hover:bg-divider hover:text-fg"
          >
            <Icon name="close" size={13} />
          </button>
        </header>
        <div className="min-h-0 overflow-y-auto pb-[env(safe-area-inset-bottom)]">
          <Section title="プロフィール">
            <div className="text-[12.5px] text-muted">
              {user?.email}
              {user && (
                <span className={user.emailVerified ? "ml-2 text-[#3c9a5f]" : "ml-2 text-accent"}>
                  {user.emailVerified ? "確認済み" : "未確認"}
                </span>
              )}
            </div>
            <div className="flex gap-2">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={60}
                aria-label="表示名"
                className={`${FIELD} h-8 text-[13px]`}
              />
              <button
                onClick={() => void saveName()}
                disabled={savingName || !name.trim() || name.trim() === user?.name}
                className={BTN}
              >
                保存
              </button>
            </div>
          </Section>

          <Section title="パスワードの変更">
            <form onSubmit={changePassword} className="flex flex-col gap-2">
              <input
                type="password"
                placeholder="現在のパスワード"
                autoComplete="current-password"
                value={pw.current}
                onChange={(e) => setPw({ ...pw, current: e.target.value })}
                required
                className={`${FIELD} h-8 text-[13px]`}
              />
              <input
                type="password"
                placeholder="新しいパスワード（8 文字以上）"
                autoComplete="new-password"
                value={pw.next}
                onChange={(e) => setPw({ ...pw, next: e.target.value })}
                required
                minLength={8}
                maxLength={128}
                className={`${FIELD} h-8 text-[13px]`}
              />
              <input
                type="password"
                placeholder="新しいパスワード（確認）"
                autoComplete="new-password"
                value={pw.confirm}
                onChange={(e) => setPw({ ...pw, confirm: e.target.value })}
                required
                className={`${FIELD} h-8 text-[13px]`}
              />
              <label className="flex cursor-pointer items-center gap-2 text-[12px] text-muted">
                <input
                  type="checkbox"
                  checked={pw.revoke}
                  onChange={(e) => setPw({ ...pw, revoke: e.target.checked })}
                  className="accent-[var(--accent)]"
                />
                ほかの端末からログアウトする
              </label>
              {pwError && <Notice tone="error">{pwError}</Notice>}
              <div>
                <button type="submit" disabled={pwBusy} className={BTN}>
                  {pwBusy && <Spinner />}
                  パスワードを変更
                </button>
              </div>
            </form>
          </Section>

          <Section title="ログイン中の端末">
            {sessions === null ? (
              <span className="text-[12.5px] text-muted">読み込み中…</span>
            ) : (
              <ul className="m-0 flex list-none flex-col gap-1 p-0">
                {sessions.map((s) => {
                  const current = s.token === currentToken;
                  return (
                    <li key={s.id} className="flex items-center gap-2.5 rounded-lg px-1 py-1.5">
                      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-surface-2 text-muted">
                        <Icon name="globe" size={14} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[12.5px] font-medium text-fg">
                          {describeAgent(s.userAgent)}
                          {current && <span className="ml-2 text-[11px] font-semibold text-accent">この端末</span>}
                        </div>
                        <div className="truncate text-[11px] text-muted">
                          {s.ipAddress ? `${s.ipAddress} · ` : ""}
                          {relativeTime(new Date(s.updatedAt))}に利用
                        </div>
                      </div>
                      {!current && (
                        <button onClick={() => void revoke(s.token)} className={BTN_GHOST}>
                          ログアウト
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
            {others > 0 && (
              <div>
                <button onClick={() => void revokeOthers()} className={BTN_GHOST}>
                  ほかの端末をすべてログアウト
                </button>
              </div>
            )}
          </Section>
        </div>
      </div>
    </div>
  );
}
