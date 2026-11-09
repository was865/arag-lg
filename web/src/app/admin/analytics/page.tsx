import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { AnalyticsView } from "@/components/admin/analytics-view";
import { getAuth } from "@/lib/auth/server";

export const metadata: Metadata = { title: "利用状況 — ARag" };

async function Guarded() {
  const session = await getAuth().api.getSession({ headers: await headers() });
  if (!session) redirect("/login?next=%2Fadmin%2Fanalytics");
  if (session.user.role !== "owner" && session.user.role !== "admin") redirect("/");
  return <AnalyticsView />;
}

export default function AnalyticsPage() {
  return (
    <Suspense fallback={<div className="h-dvh bg-bg" />}>
      <Guarded />
    </Suspense>
  );
}
