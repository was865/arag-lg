"use client";

/**
 * アカウント（specs/006-auth R11）: 表示名・パスワードの変更・ログイン中の端末。
 * 見た目は iOS / macOS の設定画面にならい、角丸のグループにまとめる。
 */
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Notice } from "@/components/auth/auth-card";
import { Spinner } from "@/components/ui/spinner";
import { Icon } from "@/components/icons";
import { useToast } from "@/components/feedback/toast-provider";
import { Button } from "@/components/ui/button";
import { ListGroup, ListItem } from "@/components/ui/list";
import { Switch } from "@/components/ui/switch";
import { authClient, authErrorMessage } from "@/lib/auth/client";
import { describeAgent } from "@/lib/auth/user";
import { cn, relativeTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

interface SessionRow {
  id: string;
  token: string;
  userAgent?: string | null;
  ipAddress?: string | null;
  updatedAt: Date | string;
}

/** 端末一覧の読み込み結果。stale = ログインから時間が経っていて一覧を見せてもらえない */
type Sessions = { state: "loading" } | { state: "ok"; rows: SessionRow[] } | { state: "stale" } | { state: "error" };

const INLINE_INPUT = "min-w-0 flex-1 border-0 bg-transparent text-body text-fg outline-none placeholder:text-muted-2";

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
        <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-accent text-title font-semibold text-white">
          {initial(user?.name, user?.email)}
        </span>
        <div className="min-w-0">
          <div className="truncate text-headline font-semibold text-fg">{user?.name || "—"}</div>
          <div className="flex min-w-0 items-center gap-1.5 text-footnote text-muted">
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

      <ListGroup title="プロフィール">
        <ListItem>
          <label htmlFor="account-name" className="w-24 shrink-0 text-body text-fg">
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
            <Button variant="plain" onClick={() => void saveName()} disabled={savingName}>
              保存
            </Button>
          )}
        </ListItem>
      </ListGroup>

      <ListGroup title="セキュリティ">
        {!pwOpen ? (
          <ListItem>
            <span className="flex-1 text-body text-fg">パスワード</span>
            <Button variant="plain" onClick={() => setPwOpen(true)}>
              変更…
            </Button>
          </ListItem>
        ) : (
          <form onSubmit={changePassword}>
            <ListItem>
              <label htmlFor="pw-current" className="w-32 shrink-0 text-body text-fg">
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
            </ListItem>
            <ListItem>
              <label htmlFor="pw-next" className="w-32 shrink-0 text-body text-fg">
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
            </ListItem>
            <ListItem>
              <label htmlFor="pw-confirm" className="w-32 shrink-0 text-body text-fg">
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
            </ListItem>
            <ListItem>
              <span className="flex-1 text-body text-fg">ほかの端末からログアウト</span>
              <Switch
                label="ほかの端末からログアウト"
                checked={pw.revoke}
                onChange={(v) => setPw({ ...pw, revoke: v })}
              />
            </ListItem>
            {pwError && (
              <div className="px-3.5 pb-1 pt-2">
                <Notice tone="error">{pwError}</Notice>
              </div>
            )}
            <ListItem className="justify-end gap-4">
              <Button variant="plain" onClick={closePassword} className="text-muted">
                キャンセル
              </Button>
              <Button type="submit" variant="primary" size="sm" disabled={pwBusy}>
                {pwBusy && <Spinner size="md" tone="current" />}
                変更
              </Button>
            </ListItem>
          </form>
        )}
      </ListGroup>

      <ListGroup
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
          <ListItem>
            <span className="text-body text-muted">読み込み中…</span>
          </ListItem>
        ) : (
          <>
            {rows.map((s) => {
              const isCurrent = s.token === current?.token;
              return (
                <ListItem key={s.id}>
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-[8px] bg-surface text-muted shadow-e1">
                    <Icon name="globe" size={15} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 text-body text-fg">
                      <span className="truncate">{describeAgent(s.userAgent)}</span>
                      {isCurrent && (
                        <Badge tone="accent">
                          この端末
                        </Badge>
                      )}
                    </div>
                    <div className="truncate text-caption text-muted">
                      {s.ipAddress ? `${s.ipAddress} · ` : ""}
                      {isCurrent ? "使用中" : `${relativeTime(new Date(s.updatedAt))}に利用`}
                    </div>
                  </div>
                  {!isCurrent && (
                    <Button variant="plain" onClick={() => void revoke(s.token)} className="text-danger">
                      ログアウト
                    </Button>
                  )}
                </ListItem>
              );
            })}
            {sessions.state === "stale" && (
              <ListItem>
                <Button variant="plain" onClick={() => void signInAgain()}>
                  再ログインしてほかの端末を表示
                </Button>
              </ListItem>
            )}
            {others > 0 && (
              <ListItem>
                <Button variant="plain" onClick={() => void revokeOthers()} className="text-danger">
                  ほかの端末をすべてログアウト
                </Button>
              </ListItem>
            )}
          </>
        )}
      </ListGroup>
    </div>
  );
}
