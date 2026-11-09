import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { DepartmentsView } from "@/components/admin/departments-view";
import { getAuth } from "@/lib/auth/server";

export const metadata: Metadata = { title: "部門 — ARag" };

/** owner・admin だけ（specs/024-kb-access）。それ以外はチャットへ戻す。 */
async function Guarded() {
  const session = await getAuth().api.getSession({ headers: await headers() });
  if (!session) redirect("/login?next=%2Fadmin%2Fdepartments");
  if (session.user.role !== "owner" && session.user.role !== "admin") redirect("/");
  return <DepartmentsView />;
}

export default function DepartmentsPage() {
  return (
    <Suspense fallback={<div className="h-dvh bg-bg" />}>
      <Guarded />
    </Suspense>
  );
}
