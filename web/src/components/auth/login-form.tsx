"use client";

/** ログイン・登録・パスワード再設定の申請（specs/006-auth R1〜R4・R9）。 */
import { useState } from "react";
import { AuthCard, FIELD, Field, LinkButton, Notice, PRIMARY, Spinner } from "@/components/auth/auth-card";
import { authClient, authErrorMessage } from "@/lib/auth/client";
import { safeNext } from "@/lib/auth/guard";

type Mode = "signin" | "signup" | "reset";

const COPY: Record<Mode, { title: string; desc: string; submit: string; busy: string }> = {
  signin: {
    title: "ログイン",
    desc: "社内文書に根拠を持って答えるナレッジアシスタントです。",
    submit: "ログイン",
    busy: "ログインしています…",
  },
  signup: {
    title: "アカウントを作成",
    desc: "登録後、確認メールのリンクを開くと質問と文書の追加ができるようになります。",
    submit: "登録する",
    busy: "登録しています…",
  },
  reset: {
    title: "パスワードの再設定",
    desc: "登録したメールアドレスに、再設定用のリンクを送ります。",
    submit: "再設定メールを送る",
    busy: "送信しています…",
  },
};

export function LoginForm({ next }: { next: string | null }) {
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [remember, setRemember] = useState(true);
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  const go = (m: Mode) => {
    setMode(m);
    setError("");
    setInfo("");
  };

  const enter = () => window.location.assign(safeNext(next));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    setInfo("");
    try {
      if (mode === "signin") {
        const { error } = await authClient.signIn.email({ email, password, rememberMe: remember });
        if (error) return setError(authErrorMessage(error));
        enter();
      } else if (mode === "signup") {
        const { error } = await authClient.signUp.email({ email, password, name: name.trim(), callbackURL: "/?verified=1" });
        if (error) return setError(authErrorMessage(error));
        enter();
      } else {
        const { error } = await authClient.requestPasswordReset({ email, redirectTo: "/reset-password" });
        if (error?.status === 429) return setError(authErrorMessage(error));
        // 登録の有無は知らせない（列挙対策）
        setMode("signin");
        setInfo("登録済みのアドレスであれば、再設定用のリンクを送りました。メールをご確認ください。");
      }
    } catch {
      setError("通信に失敗しました。時間をおいてお試しください");
    } finally {
      setBusy(false);
    }
  };

  const c = COPY[mode];
  return (
    <AuthCard
      title={c.title}
      description={c.desc}
      footer={
        mode === "signin" ? (
          <>
            はじめての方は <LinkButton onClick={() => go("signup")}>アカウントを作成</LinkButton>
          </>
        ) : (
          <LinkButton onClick={() => go("signin")}>ログインに戻る</LinkButton>
        )
      }
    >
      <form onSubmit={submit} className="flex flex-col gap-3.5" noValidate={false}>
        <Field label="メールアドレス">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            autoComplete="email"
            required
            autoFocus
            className={FIELD}
          />
        </Field>
        {mode === "signup" && (
          <Field label="表示名">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="山田 太郎"
              autoComplete="name"
              required
              maxLength={60}
              className={FIELD}
            />
          </Field>
        )}
        {mode !== "reset" && (
          <Field
            label="パスワード"
            aside={
              mode === "signin" ? <LinkButton onClick={() => go("reset")}>パスワードを忘れた場合</LinkButton> : undefined
            }
          >
            <div className="relative">
              <input
                type={showPw ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={mode === "signup" ? "8 文字以上" : ""}
                autoComplete={mode === "signin" ? "current-password" : "new-password"}
                required
                minLength={mode === "signup" ? 8 : undefined}
                maxLength={128}
                className={`${FIELD} pr-16`}
              />
              <button
                type="button"
                onClick={() => setShowPw((v) => !v)}
                className="absolute right-1.5 top-1/2 h-7 -translate-y-1/2 rounded-md px-2 text-[11.5px] font-medium text-muted hover:bg-divider hover:text-fg"
              >
                {showPw ? "隠す" : "表示"}
              </button>
            </div>
          </Field>
        )}
        {mode === "signin" && (
          <label className="flex cursor-pointer items-center gap-2 text-[12.5px] text-muted">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
              className="accent-[var(--accent)]"
            />
            ログイン状態を保持する（30 日）
          </label>
        )}
        {error && <Notice tone="error">{error}</Notice>}
        {info && <Notice tone="info">{info}</Notice>}
        <button type="submit" disabled={busy} className={`mt-1 ${PRIMARY}`}>
          {busy && <Spinner />}
          {busy ? c.busy : c.submit}
        </button>
      </form>
    </AuthCard>
  );
}
