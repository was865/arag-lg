"use client";

/** メールのリンクから新しいパスワードを設定する（specs/006-auth R9）。 */
import { useState } from "react";
import { AuthCard, FIELD, Field, Notice, PRIMARY, Spinner } from "@/components/auth/auth-card";
import { authClient, authErrorMessage } from "@/lib/auth/client";

export function ResetPasswordForm({ token, linkError }: { token: string | null; linkError: string | null }) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(linkError || !token ? authErrorMessage({ code: "INVALID_TOKEN" }) : "");
  const [done, setDone] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    if (password !== confirm) return setError("確認用のパスワードが一致しません");
    setBusy(true);
    setError("");
    try {
      const { error } = await authClient.resetPassword({ newPassword: password, token });
      if (error) return setError(authErrorMessage(error));
      setDone(true);
    } catch {
      setError("通信に失敗しました。時間をおいてお試しください");
    } finally {
      setBusy(false);
    }
  };

  const toLogin = (
    <a href="/login" className="text-[12.5px] font-medium text-accent no-underline hover:underline">
      ログイン画面へ
    </a>
  );

  if (done) {
    return (
      <AuthCard title="パスワードを変更しました" description="ほかの端末のログインは解除しました。新しいパスワードでログインしてください。" footer={toLogin}>
        <a href="/login" className={`${PRIMARY} no-underline`}>
          ログインする
        </a>
      </AuthCard>
    );
  }

  return (
    <AuthCard title="新しいパスワード" description="8 文字以上で設定してください。" footer={toLogin}>
      <form onSubmit={submit} className="flex flex-col gap-3.5">
        <Field label="新しいパスワード">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            required
            minLength={8}
            maxLength={128}
            autoFocus
            disabled={!token}
            className={FIELD}
          />
        </Field>
        <Field label="確認のためもう一度">
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
            required
            disabled={!token}
            className={FIELD}
          />
        </Field>
        {error && <Notice tone="error">{error}</Notice>}
        <button type="submit" disabled={busy || !token} className={`mt-1 ${PRIMARY}`}>
          {busy && <Spinner />}
          {busy ? "変更しています…" : "パスワードを変更"}
        </button>
      </form>
    </AuthCard>
  );
}
