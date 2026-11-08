import { Suspense } from "react";
import { connection } from "next/server";
import { apiClient } from "@/lib/api/client";

// P0 の仮画面。旧版 UI の移植は P4。
async function ApiStatus() {
  await connection();
  let label = "接続できません";
  try {
    const { data } = await apiClient().GET("/healthz");
    if (data?.status === "ok") label = "正常";
  } catch {
    // API 未起動時は「接続できません」のまま表示する
  }
  return <dd data-testid="api-status">{label}</dd>;
}

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col gap-4 p-8">
      <h1 className="text-2xl font-semibold">ARag</h1>
      <p>開発中の骨格です。</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4">
        <dt>API</dt>
        <Suspense fallback={<dd>確認中…</dd>}>
          <ApiStatus />
        </Suspense>
      </dl>
    </main>
  );
}
