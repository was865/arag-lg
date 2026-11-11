"use client";

/** メール未確認の帯（specs/006-auth R6）。質問と文書の追加は確認後にできることを伝え、確認メールを再送できる。 */
import { useState } from "react";
import { Icon } from "@/components/icons";
import { useToast } from "@/components/feedback/toast-provider";
import { authClient, authErrorMessage } from "@/lib/auth/client";
import { Button } from "@/components/ui/button";

export function UnverifiedBanner({ email }: { email: string }) {
  const push = useToast();
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  const resend = async () => {
    setBusy(true);
    try {
      const { error } = await authClient.sendVerificationEmail({ email, callbackURL: "/?verified=1" });
      if (error) push(authErrorMessage(error), "error");
      else {
        setSent(true);
        push(`${email} に確認メールを送りました`, "success");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      role="status"
      className="flex items-center gap-2.5 border-b-[0.5px] border-divider bg-accent-soft px-[18px] py-2 text-footnote text-fg max-md:px-3"
    >
      <Icon name="info" size={14} className="shrink-0 text-accent" />
      <span className="min-w-0 flex-1 leading-[1.5]">
        メールアドレスの確認が済んでいません。<span className="max-md:hidden">確認メールのリンクを開くと、質問と文書の追加ができるようになります。</span>
      </span>
      <Button variant="plain" size="sm" className="font-semibold"
        onClick={() => void resend()}
        disabled={busy || sent}
      >
        {sent ? "送信しました" : "確認メールを再送"}
      </Button>
    </div>
  );
}
