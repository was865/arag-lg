import "server-only";

/** 認証メール（確認・パスワード再設定）の送信（specs/006-auth R6・R9・R10）。
 * ARAG_SMTP_URL（例 smtp://mailpit:1025）が無ければ送らず、リンクをサーバのログに出す（開発専用）。 */
import nodemailer, { type Transporter } from "nodemailer";

let transport: Transporter | null | undefined;

function getTransport(): Transporter | null {
  if (transport === undefined) {
    const url = process.env.ARAG_SMTP_URL;
    transport = url ? nodemailer.createTransport(url) : null;
  }
  return transport;
}

const APP = "ARag";

export interface Mail {
  to: string;
  subject: string;
  text: string;
}

export function verificationMail(to: string, name: string, url: string): Mail {
  return {
    to,
    subject: `【${APP}】メールアドレスの確認`,
    text: [
      `${name || to} 様`,
      "",
      `${APP} へのご登録ありがとうございます。`,
      "次のリンクを開いて、メールアドレスを確認してください（24 時間有効）。",
      "",
      url,
      "",
      "このメールに心当たりがない場合は、破棄してください。",
    ].join("\n"),
  };
}

export function resetPasswordMail(to: string, name: string, url: string): Mail {
  return {
    to,
    subject: `【${APP}】パスワードの再設定`,
    text: [
      `${name || to} 様`,
      "",
      "パスワード再設定の申請を受け付けました。",
      "次のリンクを開いて、新しいパスワードを設定してください（1 時間有効）。",
      "",
      url,
      "",
      "申請していない場合は、このメールを破棄してください。パスワードは変わりません。",
    ].join("\n"),
  };
}

export async function sendMail(mail: Mail): Promise<void> {
  const t = getTransport();
  if (!t) {
    console.info(`[auth-mail] SMTP 未設定のため送信しません: to=${mail.to} subject=${mail.subject}\n${mail.text}`);
    return;
  }
  await t.sendMail({ from: process.env.ARAG_MAIL_FROM ?? `${APP} <no-reply@arag.local>`, ...mail });
}
