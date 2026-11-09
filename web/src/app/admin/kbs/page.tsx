import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { KbsView } from "@/components/admin/kbs-view";
import { getAuth } from "@/lib/auth/server";

export const metadata: Metadata = { title: "ナレッジベース — ARag" };

/** owner・admin だけ（specs/024-kb-access）。それ以外はチャットへ戻す。 */
async function Guarded() {
  const session = await getAuth().api.getSession({ headers: await headers() });
  if (!session) redirect("/login?next=%2Fadmin%2Fkbs");
  if (session.user.role !== "owner" && session.user.role !== "admin") redirect("/");
  return <KbsView />;
}

export default function KbsPage() {
  return (
    <Suspense fallback={<div className="h-dvh bg-bg" />}>
      <Guarded />
    </Suspense>
  );
}
