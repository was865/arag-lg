"use client";

/**
 * アカウント（specs/006-auth R11）: 表示名・パスワードの変更・ログイン中の端末。
 * 見た目は iOS / macOS の設定画面にならい、角丸のグループにまとめる。
 */
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Notice, Spinner } from "@/components/auth/auth-card";
import { Icon } from "@/components/icons";
import { useToast } from "@/components/feedback/toast-provider";
import { Switch } from "@/components/ui/switch";
import { authClient, authErrorMessage } from "@/lib/auth/client";
import { describeAgent } from "@/lib/auth/user";
import { cn, relativeTime } from "@/lib/utils";

interface SessionRow {
  id: string;
  token: string;
  userAgent?: string | null;
  ipAddress?: string | null;
  updatedAt: Date | string;
}

/** 端末一覧の読み込み結果。stale = ログインから時間が経っていて一覧を見せてもらえない */
type Sessions = { state: "loading" } | { state: "ok"; rows: SessionRow[] } | { state: "stale" } | { state: "error" };

const TEXT_BTN = "border-0 bg-transparent p-0 text-[13px] font-medium text-accent hover:opacity-80 disabled:opacity-40";
const INLINE_INPUT =
  "min-w-0 flex-1 border-0 bg-transparent text-[13px] text-fg outline-none placeholder:text-muted-2";

function Group({ title, footer, children }: { title: string; footer?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-1.5">
      <h3 className="m-0 px-3 text-[11.5px] font-medium text-muted">{title}</h3>
      <div className="overflow-hidden rounded-[12px] border-[0.5px] border-divider bg-surface-2">{children}</div>
      {footer && <p className="m-0 px-3 text-[11.5px] leading-[1.55] text-muted">{footer}</p>}
    </section>
  );
}

/** グループ内の 1 行（行の間は細い区切り線） */
function Item({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "flex min-h-[44px] items-center gap-3 px-3.5 py-2 [&+&]:border-t-[0.5px] [&+&]:border-divider",
        className,
      )}
    >
      {children}
    </div>
  );
}

function initial(name: string | undefined, email: string | undefined): string {
  return (name?.trim() || email || "?").slice(0, 1).toUpperCase();
}

/** 設定パネルの「アカウント」タブ（specs/014-settings R1）。 */
export function AccountPanel() {
  const push = useToast();
  const router = useRouter();
  const { data, refetch } = authClient.useSession();
  const user = data?.user;
  const current = data?.session;

  // 編集していなければセッションの名前を出す（読み込み前に空で固まらないように）
  const [draft, setName] = useState<string | null>(null);
  const name = draft ?? user?.name ?? "";
  const [savingName, setSavingName] = useState(false);

  const [pwOpen, setPwOpen] = useState(false);
  const [pw, setPw] = useState({ current: "", next: "", confirm: "", revoke: true });
  const [pwBusy, setPwBusy] = useState(false);
  const [pwError, setPwError] = useState("");

  const [sessions, setSessions] = useState<Sessions>({ state: "loading" });

  const loadSessions = useCallback(async () => {
    const { data, error } = await authClient.listSessions();
    if (error) {
      // Better Auth は最近ログインしたセッションにしか一覧を返さない（freshAge）
      setSessions(error.code === "SESSION_NOT_FRESH" ? { state: "stale" } : { state: "error" });
      return;
    }
    setSessions({ state: "ok", rows: (data ?? []) as SessionRow[] });
  }, []);

  useEffect(() => {
    let alive = true;
    void authClient.listSessions().then(({ data, error }) => {
      if (!alive) return;
      if (error) setSessions(error.code === "SESSION_NOT_FRESH" ? { state: "stale" } : { state: "error" });
      else setSessions({ state: "ok", rows: (data ?? []) as SessionRow[] });
    });
    return () => {
      alive = false;
    };
  }, []);

  const nameChanged = !!name.trim() && name.trim() !== user?.name;

  const saveName = async () => {
    if (!nameChanged) return;
    setSavingName(true);
    const { error } = await authClient.updateUser({ name: name.trim() });
    setSavingName(false);
    if (error) return push(authErrorMessage(error), "error");
    await refetch();
    setName(null);
    push("表示名を変更しました", "success");
  };

  const closePassword = () => {
    setPwOpen(false);
    setPwError("");
    setPw({ current: "", next: "", confirm: "", revoke: true });
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
    closePassword();
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

  const signInAgain = async () => {
    await authClient.signOut();
    router.replace("/login");
  };

  // 一覧が取れないときも、この端末だけは手元のセッションから出す
  const rows: SessionRow[] =
    sessions.state === "ok" ? sessions.rows : current ? [current as unknown as SessionRow] : [];
  const others = rows.filter((s) => s.token !== current?.token).length;

  return (
    <div className="flex flex-col gap-6 px-5 py-5">
      {/* プロフィール */}
      <div className="flex items-center gap-3.5 px-1">
        <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-accent text-[19px] font-semibold text-white">
          {initial(user?.name, user?.email)}
        </span>
        <div className="min-w-0">
          <div className="truncate text-[15px] font-semibold text-fg">{user?.name || "—"}</div>
          <div className="flex min-w-0 items-center gap-1.5 text-[12.5px] text-muted">
            <span className="truncate">{user?.email}</span>
            {user &&
              (user.emailVerified ? (
                <span className="inline-flex shrink-0 items-center gap-0.5 text-accent" title="メールアドレス確認済み">
                  <Icon name="check" size={12} />
                  確認済み
                </span>
              ) : (
                <span className="shrink-0 text-danger">未確認</span>
              ))}
          </div>
        </div>
      </div>

      <Group title="プロフィール">
        <Item>
          <label htmlFor="account-name" className="w-24 shrink-0 text-[13px] text-fg">
            表示名
          </label>
          <input
            id="account-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void saveName()}
            maxLength={60}
            className={cn(INLINE_INPUT, "text-right")}
          />
          {nameChanged && (
            <button onClick={() => void saveName()} disabled={savingName} className={TEXT_BTN}>
              保存
            </button>
          )}
        </Item>
      </Group>

      <Group title="セキュリティ">
        {!pwOpen ? (
          <Item>
            <span className="flex-1 text-[13px] text-fg">パスワード</span>
            <button onClick={() => setPwOpen(true)} className={TEXT_BTN}>
              変更…
            </button>
          </Item>
        ) : (
          <form onSubmit={changePassword}>
            <Item>
              <label htmlFor="pw-current" className="w-32 shrink-0 text-[13px] text-fg">
                現在のパスワード
              </label>
              <input
                id="pw-current"
                type="password"
                autoComplete="current-password"
                autoFocus
                value={pw.current}
                onChange={(e) => setPw({ ...pw, current: e.target.value })}
                required
                className={INLINE_INPUT}
              />
            </Item>
            <Item>
              <label htmlFor="pw-next" className="w-32 shrink-0 text-[13px] text-fg">
                新しいパスワード
              </label>
              <input
                id="pw-next"
                type="password"
                placeholder="8 文字以上"
                autoComplete="new-password"
                value={pw.next}
                onChange={(e) => setPw({ ...pw, next: e.target.value })}
                required
                minLength={8}
                maxLength={128}
                className={INLINE_INPUT}
              />
            </Item>
            <Item>
              <label htmlFor="pw-confirm" className="w-32 shrink-0 text-[13px] text-fg">
                確認
              </label>
              <input
                id="pw-confirm"
                type="password"
                placeholder="もう一度入力"
                autoComplete="new-password"
                value={pw.confirm}
                onChange={(e) => setPw({ ...pw, confirm: e.target.value })}
                required
                className={INLINE_INPUT}
              />
            </Item>
            <Item>
              <span className="flex-1 text-[13px] text-fg">ほかの端末からログアウト</span>
              <Switch
                label="ほかの端末からログアウト"
                checked={pw.revoke}
                onChange={(v) => setPw({ ...pw, revoke: v })}
              />
            </Item>
            {pwError && (
              <div className="px-3.5 pb-1 pt-2">
                <Notice tone="error">{pwError}</Notice>
              </div>
            )}
            <Item className="justify-end gap-4">
              <button type="button" onClick={closePassword} className={cn(TEXT_BTN, "text-muted")}>
                キャンセル
              </button>
              <button
                type="submit"
                disabled={pwBusy}
                className="inline-flex h-7 items-center gap-1.5 rounded-full border-0 bg-accent px-3.5 text-[12.5px] font-semibold text-white hover:brightness-105 disabled:opacity-60"
              >
                {pwBusy && <Spinner />}
                変更
              </button>
            </Item>
          </form>
        )}
      </Group>

      <Group
        title="ログイン中の端末"
        footer={
          sessions.state === "stale"
            ? "安全のため、ほかの端末はログインから 24 時間以内だけ表示します。表示するには再ログインしてください。"
            : sessions.state === "error"
              ? "端末の一覧を取得できませんでした。"
              : undefined
        }
      >
        {sessions.state === "loading" ? (
          <Item>
            <span className="text-[13px] text-muted">読み込み中…</span>
          </Item>
        ) : (
          <>
            {rows.map((s) => {
              const isCurrent = s.token === current?.token;
              return (
                <Item key={s.id}>
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-[8px] bg-surface text-muted shadow-e1">
                    <Icon name="globe" size={15} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 text-[13px] text-fg">
                      <span className="truncate">{describeAgent(s.userAgent)}</span>
                      {isCurrent && (
                        <span className="shrink-0 rounded-full bg-accent-soft px-1.5 py-px text-[10.5px] font-semibold text-accent">
                          この端末
                        </span>
                      )}
                    </div>
                    <div className="truncate text-[11.5px] text-muted">
                      {s.ipAddress ? `${s.ipAddress} · ` : ""}
                      {isCurrent ? "使用中" : `${relativeTime(new Date(s.updatedAt))}に利用`}
                    </div>
                  </div>
                  {!isCurrent && (
                    <button onClick={() => void revoke(s.token)} className={cn(TEXT_BTN, "text-danger")}>
                      ログアウト
                    </button>
                  )}
                </Item>
              );
            })}
            {sessions.state === "stale" && (
              <Item>
                <button onClick={() => void signInAgain()} className={TEXT_BTN}>
                  再ログインしてほかの端末を表示
                </button>
              </Item>
            )}
            {others > 0 && (
              <Item>
                <button onClick={() => void revokeOthers()} className={cn(TEXT_BTN, "text-danger")}>
                  ほかの端末をすべてログアウト
                </button>
              </Item>
            )}
          </>
        )}
      </Group>
    </div>
  );
}
