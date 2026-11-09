import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { AuditView } from "@/components/admin/audit-view";
import { getAuth } from "@/lib/auth/server";

export const metadata: Metadata = { title: "監査ログ — ARag" };

async function Guarded() {
  const session = await getAuth().api.getSession({ headers: await headers() });
  if (!session) redirect("/login?next=%2Fadmin%2Faudit");
  if (session.user.role !== "owner" && session.user.role !== "admin") redirect("/");
  return <AuditView />;
}

export default function AuditPage() {
  return (
    <Suspense fallback={<div className="h-dvh bg-bg" />}>
      <Guarded />
    </Suspense>
  );
}
