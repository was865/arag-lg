import type { Metadata } from "next";
import Link from "next/link";
import { headers } from "next/headers";
import { Suspense } from "react";
import { AuthCard, PRIMARY } from "@/components/auth/auth-card";
import { SharedThread, type SharedThreadData } from "@/components/share/shared-thread";
import { serverApiHeaders } from "@/lib/api/proxy-env";

// 共有ページは検索エンジンに索引させない（specs/008-thread-share R6）
export const metadata: Metadata = { title: "共有されたスレッド — ARag", robots: { index: false, follow: false } };

type Result = { ok: SharedThreadData } | { denied: "auth" | "notfound" | "error" };

async function load(token: string): Promise<Result> {
  const base = (process.env.API_BASE_URL ?? "http://localhost:8100").replace(/\/$/, "");
  try {
    const res = await fetch(`${base}/v1/shared/${encodeURIComponent(token)}`, {
      headers: await serverApiHeaders(await headers()),
      cache: "no-store",
    });
    if (res.ok) return { ok: (await res.json()) as SharedThreadData };
    if (res.status === 401) return { denied: "auth" };
    if (res.status === 404 || res.status === 422) return { denied: "notfound" };
    return { denied: "error" };
  } catch {
    return { denied: "error" };
  }
}

async function Shared({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const result = await load(token);
  if ("ok" in result) return <SharedThread thread={result.ok} />;
  if (result.denied === "auth") {
    return (
      <AuthCard title="ログインが必要です" description="このスレッドは社内の利用者だけに共有されています。">
        <Link href={`/login?next=${encodeURIComponent(`/s/${token}`)}`} className={PRIMARY}>
          ログインして読む
        </Link>
      </AuthCard>
    );
  }
  return (
    <AuthCard
      title={result.denied === "notfound" ? "スレッドが見つかりません" : "読み込めませんでした"}
      description={
        result.denied === "notfound"
          ? "リンクが間違っているか、共有が止められています。"
          : "時間をおいてもう一度お試しください。"
      }
    >
      <Link href="/" className={PRIMARY}>
        ARag を開く
      </Link>
    </AuthCard>
  );
}

export default function SharedPage({ params }: { params: Promise<{ token: string }> }) {
  return (
    <Suspense fallback={<div className="h-dvh bg-bg" />}>
      <Shared params={params} />
    </Suspense>
  );
}
