import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { SystemsView } from "@/components/admin/systems-view";
import { getAuth } from "@/lib/auth/server";

export const metadata: Metadata = { title: "社内システム — ARag" };

/** owner・admin だけ（specs/032）。それ以外はチャットへ戻す。 */
async function Guarded() {
  const session = await getAuth().api.getSession({ headers: await headers() });
  if (!session) redirect("/login?next=%2Fadmin%2Fsystems");
  if (session.user.role !== "owner" && session.user.role !== "admin") redirect("/");
  return <SystemsView />;
}

export default function SystemsPage() {
  return (
    <Suspense fallback={<div className="h-dvh bg-bg" />}>
      <Guarded />
    </Suspense>
  );
}
