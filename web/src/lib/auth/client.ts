"use client";

/** ブラウザ側の Better Auth クライアント（/api/auth/*）。 */
import { adminClient } from "better-auth/client/plugins";
import { adminAc, userAc } from "better-auth/plugins/admin/access";
import { createAuthClient } from "better-auth/react";

export const authClient = createAuthClient({
  plugins: [adminClient({ roles: { owner: adminAc, admin: adminAc, member: userAc } })],
});

/** Better Auth のエラーコード → 日本語。知らないコードは汎用の文言。 */
export function authErrorMessage(error: { code?: string; status?: number; message?: string } | null | undefined): string {
  if (!error) return "";
  if (error.status === 429) return "試行回数が多すぎます。しばらくしてからお試しください";
  switch (error.code) {
    case "INVALID_EMAIL_OR_PASSWORD":
    case "INVALID_EMAIL":
    case "INVALID_PASSWORD":
      return "メールアドレスまたはパスワードが正しくありません";
    case "USER_ALREADY_EXISTS":
    case "USER_ALREADY_EXISTS_USE_ANOTHER_EMAIL":
      return "このメールアドレスは登録できません。別のアドレスか、ログインをお試しください";
    case "PASSWORD_TOO_SHORT":
      return "パスワードは 8 文字以上にしてください";
    case "PASSWORD_TOO_LONG":
      return "パスワードは 128 文字以内にしてください";
    case "INVALID_TOKEN":
      return "リンクが無効か、期限が切れています。もう一度申請してください";
    case "BANNED_USER":
      return "このアカウントは利用できません。管理者にお問い合わせください";
    case "CREDENTIAL_ACCOUNT_NOT_FOUND":
      return "パスワードが設定されていないアカウントです";
    default:
      return "うまくいきませんでした。時間をおいてお試しください";
  }
}
