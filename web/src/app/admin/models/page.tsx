import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { ModelsView } from "@/components/admin/models-view";
import { getAuth } from "@/lib/auth/server";

export const metadata: Metadata = { title: "モデル — ARag" };

async function Guarded() {
  const session = await getAuth().api.getSession({ headers: await headers() });
  if (!session) redirect("/login?next=%2Fadmin%2Fmodels");
  if (session.user.role !== "owner" && session.user.role !== "admin") redirect("/");
  return <ModelsView />;
}

export default function ModelsPage() {
  return (
    <Suspense fallback={<div className="h-dvh bg-bg" />}>
      <Guarded />
    </Suspense>
  );
}
