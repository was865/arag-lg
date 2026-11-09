import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { MembersView } from "@/components/admin/members-view";
import { getAuth } from "@/lib/auth/server";

export const metadata: Metadata = { title: "メンバー — ARag" };

/** owner・admin だけ（specs/010-admin-members R1）。それ以外はチャットへ戻す。 */
async function Guarded() {
  const session = await getAuth().api.getSession({ headers: await headers() });
  if (!session) redirect("/login?next=%2Fadmin%2Fmembers");
  if (session.user.role !== "owner" && session.user.role !== "admin") redirect("/");
  return <MembersView />;
}

export default function MembersPage() {
  return (
    <Suspense fallback={<div className="h-dvh bg-bg" />}>
      <Guarded />
    </Suspense>
  );
}
