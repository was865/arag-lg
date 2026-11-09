import type { Metadata } from "next";
import { Suspense } from "react";
import { ResetPasswordForm } from "@/components/auth/reset-password-form";

export const metadata: Metadata = { title: "パスワードの再設定 — ARag" };

type Search = Promise<Record<string, string | string[] | undefined>>;

async function Reset({ searchParams }: { searchParams: Search }) {
  const { token, error } = await searchParams;
  return (
    <ResetPasswordForm
      token={typeof token === "string" ? token : null}
      linkError={typeof error === "string" ? error : null}
    />
  );
}

export default function ResetPasswordPage({ searchParams }: { searchParams: Search }) {
  return (
    <Suspense fallback={<div className="h-dvh bg-bg" />}>
      <Reset searchParams={searchParams} />
    </Suspense>
  );
}
